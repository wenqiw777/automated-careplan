from django.shortcuts import render, redirect
from django.http import HttpResponse
from anthropic import Anthropic

ORDERS = {}
NEXT_ID = 1


def form_view(request):
    return render(request, 'form.html')


def submit_view(request):
    global NEXT_ID

    data = {
        'patient_first_name': request.POST.get('patient_first_name', ''),
        'patient_last_name': request.POST.get('patient_last_name', ''),
        'patient_mrn': request.POST.get('patient_mrn', ''),
        'patient_dob': request.POST.get('patient_dob', ''),
        'primary_diagnosis': request.POST.get('primary_diagnosis', ''),
        'additional_diagnoses': request.POST.get('additional_diagnoses', ''),
        'medication_name': request.POST.get('medication_name', ''),
        'medication_history': request.POST.get('medication_history', ''),
        'patient_records': request.POST.get('patient_records', ''),
        'provider_name': request.POST.get('provider_name', ''),
        'provider_npi': request.POST.get('provider_npi', ''),
    }

    care_plan = generate_care_plan(data)

    order_id = NEXT_ID
    NEXT_ID += 1
    ORDERS[order_id] = {'data': data, 'care_plan': care_plan}

    return redirect('order_detail', order_id=order_id)


def order_detail(request, order_id):
    order = ORDERS[order_id]
    return render(request, 'result.html', {'order': order, 'order_id': order_id})


def download_care_plan(request, order_id):
    order = ORDERS[order_id]
    response = HttpResponse(order['care_plan'], content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="care_plan_{order_id}.txt"'
    return response


def generate_care_plan(data):
    client = Anthropic()

    prompt = f"""You are a clinical pharmacist writing a care plan for a specialty pharmacy patient.

Patient: {data['patient_first_name']} {data['patient_last_name']}
MRN: {data['patient_mrn']}
DOB: {data['patient_dob']}
Primary Diagnosis (ICD-10): {data['primary_diagnosis']}
Additional Diagnoses: {data['additional_diagnoses']}
Medication: {data['medication_name']}
Medication History: {data['medication_history']}
Patient Records: {data['patient_records']}
Referring Provider: {data['provider_name']} (NPI: {data['provider_npi']})

Write a structured care plan with these four sections:
1. Problem list / Drug therapy problems
2. Goals (SMART)
3. Pharmacist interventions / plan
4. Monitoring plan & lab schedule

Use plain text. Be specific and clinically appropriate."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
