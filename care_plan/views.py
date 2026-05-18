from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import CarePlan
from .serializers import parse_submit_post, serialize_care_plan_list, serialize_care_plan_status
from .services import create_care_plan, get_care_plan_event_stream, list_care_plans_by_mrn


def form_view(request):
    return render(request, 'form.html')


def submit_view(request):
    print("\n[1] VIEW 入口 - request.POST (QueryDict):", dict(request.POST))
    patient_data, provider_data, order_data = parse_submit_post(request.POST)
    print("[2] SERIALIZER 返回 - patient_data:", patient_data)
    print("[2] SERIALIZER 返回 - provider_data:", provider_data)
    print("[2] SERIALIZER 返回 - order_data:", order_data)
    care_plan = create_care_plan(patient_data, provider_data, order_data)
    print("[3] SERVICE 返回 - care_plan.id:", care_plan.id, "status:", care_plan.status)
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


def care_plan_sse(request, care_plan_id):
    response = StreamingHttpResponse(
        get_care_plan_event_stream(care_plan_id),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def care_plan_status(request, care_plan_id):
    care_plan = get_object_or_404(CarePlan, pk=care_plan_id)
    return JsonResponse(serialize_care_plan_status(care_plan))


def get_care_plans_by_mrn(request):
    mrn = request.GET.get('mrn', '')
    if mrn == '':
        return JsonResponse({'error': 'MRN is required'}, status=400)
    care_plans = list_care_plans_by_mrn(mrn)
    return JsonResponse({'care_plans': serialize_care_plan_list(care_plans)})
