"""
共享 fixtures — 所有测试文件都可以直接用这里定义的 fixture。
pytest 会自动发现 conftest.py 并注入。
"""
import pytest
from datetime import date

from care_plan.models import CarePlan, Order, Patient, Provider


# ─── 原始数据字典（用于传给 service 函数）───

@pytest.fixture
def patient_data():
    return {'name': 'John Doe', 'mrn': 'MRN001', 'dob': '1990-01-15'}


@pytest.fixture
def provider_data():
    return {'name': 'Dr. Smith', 'npi': '1234567890'}


@pytest.fixture
def order_data():
    return {
        'medication': 'Humira',
        'diagnosis': 'Rheumatoid Arthritis',
        'medical_record': 'Patient history notes',
    }


# ─── DB model instances（已存入数据库的对象）───

@pytest.fixture
def patient(db):
    return Patient.objects.create(name='John Doe', mrn='MRN001', dob=date(1990, 1, 15))


@pytest.fixture
def provider(db):
    return Provider.objects.create(name='Dr. Smith', npi='1234567890')


@pytest.fixture
def order(db, patient, provider):
    return Order.objects.create(
        patient=patient,
        provider=provider,
        medication='Humira',
        diagnosis='Rheumatoid Arthritis',
        medical_record='Patient history notes',
    )


@pytest.fixture
def care_plan(db, order):
    return CarePlan.objects.create(order=order, status=CarePlan.Status.PENDING)
