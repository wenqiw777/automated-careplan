import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse

from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_care_plan

logger = logging.getLogger(__name__)


def form_view(request):
    return render(request, 'form.html')


def submit_view(request):
    full_name = (
        f"{request.POST.get('patient_first_name', '').strip()} "
        f"{request.POST.get('patient_last_name', '').strip()}"
    ).strip()

    patient, _ = Patient.objects.get_or_create(
        mrn=request.POST.get('patient_mrn', ''),
        defaults={
            'name': full_name,
            'dob': request.POST.get('patient_dob') or None,
        },
    )

    provider, _ = Provider.objects.get_or_create(
        npi=request.POST.get('provider_npi', ''),
        defaults={'name': request.POST.get('provider_name', '')},
    )

    diagnosis = request.POST.get('primary_diagnosis', '')
    if request.POST.get('additional_diagnoses'):
        diagnosis = f"{diagnosis}; {request.POST.get('additional_diagnoses')}"

    medical_record_parts = []
    if request.POST.get('medication_history'):
        medical_record_parts.append(f"Medication history: {request.POST.get('medication_history')}")
    if request.POST.get('patient_records'):
        medical_record_parts.append(f"Records: {request.POST.get('patient_records')}")

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=request.POST.get('medication_name', ''),
        diagnosis=diagnosis,
        medical_record="\n\n".join(medical_record_parts),
    )

    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )

    logger.info("已写入 DB：CarePlan #%d (status=pending)", care_plan.id)

    generate_care_plan.delay(care_plan.id)
    logger.info("已派发 Celery 任务：care_plan_id=%d", care_plan.id)

    return redirect('care_plan_detail', care_plan_id=care_plan.id)


def care_plan_detail(request, care_plan_id):
    care_plan = get_object_or_404(
        CarePlan.objects.select_related('order__patient', 'order__provider'),
        pk=care_plan_id,
    )
    return render(request, 'result.html', {'care_plan': care_plan})


def download_care_plan(request, care_plan_id):
    care_plan = get_object_or_404(CarePlan, pk=care_plan_id)
    content = care_plan.content or '(care plan still being generated)'
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="care_plan_{care_plan_id}.txt"'
    return response


def get_care_plans_by_mrn(request):
    mrn = request.GET.get('mrn', '')
    if mrn == '':
        return JsonResponse({'error': 'MRN is required'}, status=400)

    care_plans = (
        CarePlan.objects
        .filter(order__patient__mrn=mrn)
        .select_related('order__patient', 'order__provider')
        .order_by('-created_at')
    )

    result = [
        {
            'care_plan_id': cp.id,
            'order_id': cp.order.id,
            'medication': cp.order.medication,
            'status': cp.status,
            'content': cp.content,
            'created_at': cp.created_at.isoformat(),
        }
        for cp in care_plans
    ]
    return JsonResponse({'care_plans': result})
