"""
Integration tests — 通过 Django test client 测试完整 HTTP 链路：
URL routing → middleware → view → serializer → service → DB → response

这些测试验证各层之间的"接线"是否正确。
"""
import json
from datetime import date

import pytest
from django.test import Client
from unittest.mock import patch

from care_plan.models import CarePlan, Order, Patient, Provider

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    return Client()


# ═══════════════════════════════════════════════════
#  GET / — 表单页面
# ═══════════════════════════════════════════════════

class TestFormView:

    def test_renders_form_page(self, client, db):
        response = client.get('/')
        assert response.status_code == 200


# ═══════════════════════════════════════════════════
#  POST /submit/ — 提交表单 → 创建 care plan
# ═══════════════════════════════════════════════════

class TestSubmitView:

    @patch('care_plan.services.generate_care_plan.delay')
    def test_happy_path_redirects(self, mock_delay, client, db):
        response = client.post('/submit/', {
            'patient_first_name': 'Test',
            'patient_last_name': 'User',
            'patient_mrn': 'INT001',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'RA',
            'medication_name': 'Humira',
            'provider_name': 'Dr. Test',
            'provider_npi': '1234567890',
        })
        assert response.status_code == 302
        assert CarePlan.objects.count() == 1
        assert Patient.objects.count() == 1
        assert Provider.objects.count() == 1
        mock_delay.assert_called_once()

    @patch('care_plan.services.generate_care_plan.delay')
    def test_provider_npi_conflict_returns_409(self, mock_delay, client, db):
        Provider.objects.create(name='Dr. Original', npi='1234567890')
        response = client.post('/submit/', {
            'patient_first_name': 'Test',
            'patient_last_name': 'User',
            'patient_mrn': 'INT002',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'RA',
            'medication_name': 'Humira',
            'provider_name': 'Dr. Imposter',
            'provider_npi': '1234567890',
        })
        assert response.status_code == 409
        data = json.loads(response.content)
        assert data['code'] == 'PROVIDER_NPI_CONFLICT'
        assert data['type'] == 'block_error'
        mock_delay.assert_not_called()

    @patch('care_plan.services.generate_care_plan.delay')
    def test_patient_mrn_mismatch_returns_warning(self, mock_delay, client, db):
        Patient.objects.create(name='Original Name', mrn='INT003', dob=date(1990, 1, 15))
        response = client.post('/submit/', {
            'patient_first_name': 'Different',
            'patient_last_name': 'Person',
            'patient_mrn': 'INT003',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'RA',
            'medication_name': 'Humira',
            'provider_name': 'Dr. Test',
            'provider_npi': '9999999999',
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['type'] == 'warning'
        assert data['code'] == 'PATIENT_MRN_MISMATCH'
        mock_delay.assert_not_called()

    @patch('care_plan.services.generate_care_plan.delay')
    def test_same_day_order_duplicate_returns_409(self, mock_delay, client, db):
        # 第一次提交
        client.post('/submit/', {
            'patient_first_name': 'Test',
            'patient_last_name': 'User',
            'patient_mrn': 'DUP001',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'RA',
            'medication_name': 'Humira',
            'provider_name': 'Dr. Test',
            'provider_npi': '1111111111',
        })
        # 同一天再交一次完全一样的
        response = client.post('/submit/', {
            'patient_first_name': 'Test',
            'patient_last_name': 'User',
            'patient_mrn': 'DUP001',
            'patient_dob': '1990-01-15',
            'primary_diagnosis': 'RA',
            'medication_name': 'Humira',
            'provider_name': 'Dr. Test',
            'provider_npi': '1111111111',
        })
        assert response.status_code == 409
        data = json.loads(response.content)
        assert data['code'] == 'ORDER_SAME_DAY_DUPLICATE'


# ═══════════════════════════════════════════════════
#  GET /care-plans/<id>/ — 详情页
# ═══════════════════════════════════════════════════

class TestCarePlanDetail:

    def test_renders_detail(self, client, care_plan):
        response = client.get(f'/care-plans/{care_plan.id}/')
        assert response.status_code == 200

    def test_404_for_nonexistent(self, client, db):
        response = client.get('/care-plans/99999/')
        assert response.status_code == 404


# ═══════════════════════════════════════════════════
#  GET /care-plans/<id>/status/ — JSON 状态查询
# ═══════════════════════════════════════════════════

class TestCarePlanStatus:

    def test_pending_status(self, client, care_plan):
        response = client.get(f'/care-plans/{care_plan.id}/status/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'pending'
        assert 'content' not in data

    def test_completed_includes_content(self, client, care_plan):
        care_plan.status = CarePlan.Status.COMPLETED
        care_plan.content = 'Generated plan'
        care_plan.save()
        response = client.get(f'/care-plans/{care_plan.id}/status/')
        data = json.loads(response.content)
        assert data['status'] == 'completed'
        assert data['content'] == 'Generated plan'


# ═══════════════════════════════════════════════════
#  GET /care-plans/<id>/download/ — 下载
# ═══════════════════════════════════════════════════

class TestDownloadCarePlan:

    def test_download_completed(self, client, care_plan):
        care_plan.status = CarePlan.Status.COMPLETED
        care_plan.content = 'Full care plan text'
        care_plan.save()
        response = client.get(f'/care-plans/{care_plan.id}/download/')
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/plain'
        assert b'Full care plan text' in response.content

    def test_download_pending_shows_placeholder(self, client, care_plan):
        response = client.get(f'/care-plans/{care_plan.id}/download/')
        assert response.status_code == 200
        assert b'still being generated' in response.content


# ═══════════════════════════════════════════════════
#  GET /care-plans/?mrn=xxx — 按 MRN 查询
# ═══════════════════════════════════════════════════

class TestGetCarePlansByMrn:

    def test_returns_care_plans(self, client, care_plan, patient):
        response = client.get(f'/care-plans/?mrn={patient.mrn}')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['care_plans']) == 1
        assert data['care_plans'][0]['care_plan_id'] == care_plan.id

    def test_missing_mrn_returns_400(self, client, db):
        response = client.get('/care-plans/')
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['code'] == 'MRN_REQUIRED'

    def test_empty_mrn_returns_400(self, client, db):
        response = client.get('/care-plans/?mrn=')
        assert response.status_code == 400

    def test_unknown_mrn_returns_empty_list(self, client, db):
        response = client.get('/care-plans/?mrn=NOBODY')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['care_plans'] == []
