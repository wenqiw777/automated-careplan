from .models import CarePlan


def parse_submit_post(post_data):
    print("\n[2a] SERIALIZER 入口 - 原始 post_data:", dict(post_data))
    full_name = (
        f"{post_data.get('patient_first_name', '').strip()} "
        f"{post_data.get('patient_last_name', '').strip()}"
    ).strip()

    diagnosis = post_data.get('primary_diagnosis', '')
    if post_data.get('additional_diagnoses'):
        diagnosis = f"{diagnosis}; {post_data.get('additional_diagnoses')}"

    medical_record_parts = []
    if post_data.get('medication_history'):
        medical_record_parts.append(f"Medication history: {post_data.get('medication_history')}")
    if post_data.get('patient_records'):
        medical_record_parts.append(f"Records: {post_data.get('patient_records')}")

    patient_data = {
        'name': full_name,
        'mrn': post_data.get('patient_mrn', ''),
        'dob': post_data.get('patient_dob') or None,
    }
    provider_data = {
        'npi': post_data.get('provider_npi', ''),
        'name': post_data.get('provider_name', ''),
    }
    order_data = {
        'medication': post_data.get('medication_name', ''),
        'diagnosis': diagnosis,
        'medical_record': "\n\n".join(medical_record_parts),
    }
    confirm = post_data.get('confirm', '').lower() == 'true'
    return patient_data, provider_data, order_data, confirm


def serialize_care_plan_status(care_plan):
    data = {'status': care_plan.status}
    if care_plan.status == CarePlan.Status.COMPLETED:
        data['content'] = care_plan.content
    return data


def serialize_care_plan_list(care_plans):
    return [
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
