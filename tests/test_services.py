"""
Unit tests for care_plan/services.py
重点覆盖：Patient/Provider 重复检测 + Order 重复检测 + create_care_plan 主流程
"""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import patch

from care_plan.exceptions import BlockError, WarningException
from care_plan.models import CarePlan, Order, Patient, Provider
from care_plan.services import (
    _check_duplicate_order,
    _resolve_patient,
    _resolve_provider,
    create_care_plan,
    list_care_plans_by_mrn,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════
#  _resolve_provider — Provider 重复检测
# ═══════════════════════════════════════════════════

class TestResolveProvider:
    """三条路径：新建 / 完全匹配返回已有 / NPI 冲突报 BlockError"""

    def test_creates_new_provider(self, db):
        result = _resolve_provider({'npi': '1111111111', 'name': 'Dr. New'})
        assert result.npi == '1111111111'
        assert result.name == 'Dr. New'
        assert Provider.objects.count() == 1

    def test_returns_existing_on_exact_match(self, provider):
        result = _resolve_provider({'npi': provider.npi, 'name': provider.name})
        assert result.pk == provider.pk
        assert Provider.objects.count() == 1

    def test_raises_block_on_npi_conflict(self, provider):
        with pytest.raises(BlockError) as exc_info:
            _resolve_provider({'npi': provider.npi, 'name': 'Dr. Imposter'})
        assert exc_info.value.code == 'PROVIDER_NPI_CONFLICT'
        assert exc_info.value.http_status == 409


# ═══════════════════════════════════════════════════
#  _resolve_patient — Patient 重复检测（核心）
# ═══════════════════════════════════════════════════

class TestResolvePatient:
    """
    五条路径：
    1. DB 里没有 → 新建
    2. MRN + name + dob 完全匹配 → 返回已有
    3. MRN 匹配但 name 不同 → WarningException(PATIENT_MRN_MISMATCH)
    4. MRN 匹配但 dob 不同 → WarningException(PATIENT_MRN_MISMATCH)
    5. name + dob 匹配但 MRN 不同 → WarningException(PATIENT_IDENTITY_CONFLICT)
    """

    def test_creates_new_patient(self, db):
        result = _resolve_patient({
            'mrn': 'NEW001', 'name': 'Alice Wonder', 'dob': date(1985, 5, 20),
        })
        assert result.mrn == 'NEW001'
        assert result.name == 'Alice Wonder'
        assert Patient.objects.count() == 1

    def test_returns_existing_on_exact_match(self, patient):
        result = _resolve_patient({
            'mrn': patient.mrn, 'name': patient.name, 'dob': patient.dob,
        })
        assert result.pk == patient.pk
        assert Patient.objects.count() == 1

    def test_warns_on_mrn_match_name_different(self, patient):
        with pytest.raises(WarningException) as exc_info:
            _resolve_patient({
                'mrn': patient.mrn, 'name': 'Totally Different', 'dob': patient.dob,
            })
        assert exc_info.value.code == 'PATIENT_MRN_MISMATCH'
        assert exc_info.value.detail['existing']['name'] == patient.name
        assert exc_info.value.detail['requested']['name'] == 'Totally Different'

    def test_warns_on_mrn_match_dob_different(self, patient):
        with pytest.raises(WarningException) as exc_info:
            _resolve_patient({
                'mrn': patient.mrn, 'name': patient.name, 'dob': date(2000, 12, 25),
            })
        assert exc_info.value.code == 'PATIENT_MRN_MISMATCH'

    def test_warns_on_identity_match_mrn_different(self, patient):
        with pytest.raises(WarningException) as exc_info:
            _resolve_patient({
                'mrn': 'DIFFERENT_MRN', 'name': patient.name, 'dob': patient.dob,
            })
        assert exc_info.value.code == 'PATIENT_IDENTITY_CONFLICT'
        assert exc_info.value.detail['existing_mrn'] == patient.mrn
        assert exc_info.value.detail['requested_mrn'] == 'DIFFERENT_MRN'


# ═══════════════════════════════════════════════════
#  _check_duplicate_order — Order 重复检测
# ═══════════════════════════════════════════════════

class TestCheckDuplicateOrder:
    """
    四条路径：
    1. 无重复 → 通过
    2. 当天重复 → BlockError（即使 confirm=True 也拦截）
    3. 历史重复 + confirm=False → WarningException
    4. 历史重复 + confirm=True → 通过
    """

    def test_no_duplicate_passes(self, patient):
        _check_duplicate_order(patient, 'BrandNewDrug', confirm=False)

    def test_same_day_duplicate_blocks(self, patient, order):
        with pytest.raises(BlockError) as exc_info:
            _check_duplicate_order(patient, order.medication, confirm=False)
        assert exc_info.value.code == 'ORDER_SAME_DAY_DUPLICATE'

    def test_same_day_duplicate_blocks_even_with_confirm(self, patient, order):
        with pytest.raises(BlockError) as exc_info:
            _check_duplicate_order(patient, order.medication, confirm=True)
        assert exc_info.value.code == 'ORDER_SAME_DAY_DUPLICATE'

    def test_historical_duplicate_warns_without_confirm(self, patient, provider):
        old_order = Order.objects.create(
            patient=patient, provider=provider,
            medication='HistoricalDrug', diagnosis='Dx', medical_record='Notes',
        )
        # 把 created_at 改到过去，让它不属于"今天"
        Order.objects.filter(pk=old_order.pk).update(
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(WarningException) as exc_info:
            _check_duplicate_order(patient, 'HistoricalDrug', confirm=False)
        assert exc_info.value.code == 'ORDER_HISTORY_DUPLICATE'

    def test_historical_duplicate_passes_with_confirm(self, patient, provider):
        old_order = Order.objects.create(
            patient=patient, provider=provider,
            medication='HistoricalDrug', diagnosis='Dx', medical_record='Notes',
        )
        Order.objects.filter(pk=old_order.pk).update(
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

        # confirm=True 应该跳过历史重复警告
        _check_duplicate_order(patient, 'HistoricalDrug', confirm=True)


# ═══════════════════════════════════════════════════
#  create_care_plan — 主流程 orchestration
# ═══════════════════════════════════════════════════

class TestCreateCarePlan:
    """测试 create_care_plan 的 happy path 和各种 error path，mock 掉 Celery task"""

    @patch('care_plan.services.generate_care_plan.delay')
    def test_happy_path_creates_all_objects(self, mock_delay, db):
        cp = create_care_plan(
            patient_data={'name': 'Happy User', 'mrn': 'HP001', 'dob': date(1990, 1, 1)},
            provider_data={'name': 'Dr. Happy', 'npi': '5555555555'},
            order_data={
                'medication': 'Keytruda',
                'diagnosis': 'Cancer',
                'medical_record': 'Chart notes',
            },
        )
        assert cp.status == CarePlan.Status.PENDING
        assert cp.order.medication == 'Keytruda'
        assert cp.order.patient.name == 'Happy User'
        assert cp.order.provider.npi == '5555555555'
        mock_delay.assert_called_once_with(cp.id)

    @patch('care_plan.services.generate_care_plan.delay')
    def test_provider_conflict_stops_before_celery(self, mock_delay, provider):
        with pytest.raises(BlockError):
            create_care_plan(
                patient_data={'name': 'Any', 'mrn': 'X001', 'dob': date(1990, 1, 1)},
                provider_data={'npi': provider.npi, 'name': 'Wrong Name'},
                order_data={'medication': 'Med', 'diagnosis': 'Dx', 'medical_record': 'N'},
            )
        mock_delay.assert_not_called()

    @patch('care_plan.services.generate_care_plan.delay')
    def test_patient_mismatch_stops_before_celery(self, mock_delay, patient):
        with pytest.raises(WarningException):
            create_care_plan(
                patient_data={'name': 'Wrong Name', 'mrn': patient.mrn, 'dob': patient.dob},
                provider_data={'name': 'Dr. A', 'npi': '6666666666'},
                order_data={'medication': 'Med', 'diagnosis': 'Dx', 'medical_record': 'N'},
            )
        mock_delay.assert_not_called()

    @patch('care_plan.services.generate_care_plan.delay')
    def test_same_day_order_duplicate_stops_before_celery(self, mock_delay, patient, order):
        with pytest.raises(BlockError):
            create_care_plan(
                patient_data={'name': patient.name, 'mrn': patient.mrn, 'dob': patient.dob},
                provider_data={'name': 'Dr. New', 'npi': '7777777777'},
                order_data={
                    'medication': order.medication,
                    'diagnosis': 'Dx',
                    'medical_record': 'N',
                },
            )
        mock_delay.assert_not_called()


# ═══════════════════════════════════════════════════
#  list_care_plans_by_mrn
# ═══════════════════════════════════════════════════

class TestListCarePlansByMrn:

    def test_returns_care_plans_for_known_mrn(self, care_plan, patient):
        result = list(list_care_plans_by_mrn(patient.mrn))
        assert len(result) == 1
        assert result[0].pk == care_plan.pk

    def test_returns_empty_for_unknown_mrn(self, db):
        result = list(list_care_plans_by_mrn('NONEXISTENT'))
        assert len(result) == 0
