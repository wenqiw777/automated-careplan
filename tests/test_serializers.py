"""
Unit tests for care_plan/serializers.py
覆盖 parse_submit_post / serialize_care_plan_status / serialize_care_plan_list
"""
import pytest
from django.http import QueryDict

from care_plan.models import CarePlan
from care_plan.serializers import (
    parse_submit_post,
    serialize_care_plan_list,
    serialize_care_plan_status,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════
#  parse_submit_post — 表单数据 → 结构化字典
# ═══════════════════════════════════════════════════

class TestParseSubmitPost:

    def test_full_data(self):
        post = QueryDict(mutable=True)
        post.update({
            'patient_first_name': 'John',
            'patient_last_name': 'Doe',
            'patient_mrn': 'MRN001',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'Rheumatoid Arthritis',
            'additional_diagnoses': 'Diabetes',
            'medication_name': 'Humira',
            'medication_history': 'Prior biologics failed',
            'patient_records': 'Lab results attached',
            'provider_name': 'Dr. Smith',
            'provider_npi': '1234567890',
            'confirm': 'true',
        })
        patient, provider, order, confirm = parse_submit_post(post)

        assert patient['name'] == 'John Doe'
        assert patient['mrn'] == 'MRN001'
        assert patient['dob'] == '1990-01-15'
        assert provider['name'] == 'Dr. Smith'
        assert provider['npi'] == '1234567890'
        assert order['medication'] == 'Humira'
        assert 'Rheumatoid Arthritis; Diabetes' == order['diagnosis']
        assert 'Medication history: Prior biologics failed' in order['medical_record']
        assert 'Records: Lab results attached' in order['medical_record']
        assert confirm is True

    def test_minimal_data(self):
        post = QueryDict(mutable=True)
        post.update({
            'patient_first_name': 'Jane',
            'patient_mrn': 'MRN002',
            'primary_diagnosis': 'Cancer',
            'medication_name': 'Keytruda',
            'provider_name': 'Dr. Lee',
            'provider_npi': '9876543210',
        })
        patient, provider, order, confirm = parse_submit_post(post)

        assert patient['name'] == 'Jane'
        assert order['medical_record'] == ''
        assert confirm is False

    def test_name_strips_whitespace(self):
        post = QueryDict(mutable=True)
        post.update({'patient_first_name': '  Alice  ', 'patient_last_name': '  Wang  '})
        patient, _, _, _ = parse_submit_post(post)
        assert patient['name'] == 'Alice Wang'

    def test_confirm_false_by_default(self):
        post = QueryDict(mutable=True)
        _, _, _, confirm = parse_submit_post(post)
        assert confirm is False

    def test_confirm_case_insensitive(self):
        post = QueryDict(mutable=True)
        post.update({'confirm': 'True'})
        _, _, _, confirm = parse_submit_post(post)
        assert confirm is True

    def test_dob_none_when_empty(self):
        post = QueryDict(mutable=True)
        post.update({'patient_dob': ''})
        patient, _, _, _ = parse_submit_post(post)
        assert patient['dob'] is None

    def test_diagnosis_no_additional(self):
        post = QueryDict(mutable=True)
        post.update({'primary_diagnosis': 'RA'})
        _, _, order, _ = parse_submit_post(post)
        assert order['diagnosis'] == 'RA'

    def test_medical_record_only_history(self):
        post = QueryDict(mutable=True)
        post.update({'medication_history': 'Prior meds'})
        _, _, order, _ = parse_submit_post(post)
        assert order['medical_record'] == 'Medication history: Prior meds'


# ═══════════════════════════════════════════════════
#  serialize_care_plan_status
# ═══════════════════════════════════════════════════

class TestSerializeCarePlanStatus:

    def test_pending_status(self, care_plan):
        data = serialize_care_plan_status(care_plan)
        assert data == {'status': 'pending'}
        assert 'content' not in data

    def test_completed_includes_content(self, care_plan):
        care_plan.status = CarePlan.Status.COMPLETED
        care_plan.content = 'Generated care plan text'
        data = serialize_care_plan_status(care_plan)
        assert data['status'] == 'completed'
        assert data['content'] == 'Generated care plan text'

    def test_failed_no_content(self, care_plan):
        care_plan.status = CarePlan.Status.FAILED
        data = serialize_care_plan_status(care_plan)
        assert data == {'status': 'failed'}

    def test_processing_no_content(self, care_plan):
        care_plan.status = CarePlan.Status.PROCESSING
        data = serialize_care_plan_status(care_plan)
        assert data == {'status': 'processing'}


# ═══════════════════════════════════════════════════
#  serialize_care_plan_list
# ═══════════════════════════════════════════════════

class TestSerializeCarePlanList:

    def test_single_item(self, care_plan):
        result = serialize_care_plan_list([care_plan])
        assert len(result) == 1
        item = result[0]
        assert item['care_plan_id'] == care_plan.id
        assert item['order_id'] == care_plan.order.id
        assert item['medication'] == 'Humira'
        assert item['status'] == 'pending'

    def test_empty_list(self):
        assert serialize_care_plan_list([]) == []
