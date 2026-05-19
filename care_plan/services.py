import json
import logging
import time
from datetime import date

import redis as redis_lib
from django.conf import settings

from .exceptions import BlockError, WarningException
from .models import CarePlan, Order, Patient, Provider
from .tasks import generate_care_plan

logger = logging.getLogger(__name__)


def _resolve_provider(provider_data):
    try:
        existing = Provider.objects.get(npi=provider_data['npi'])
    except Provider.DoesNotExist:
        return Provider.objects.create(npi=provider_data['npi'], name=provider_data['name'])

    if existing.name != provider_data['name']:
        raise BlockError(
            code='PROVIDER_NPI_CONFLICT',
            message=f"NPI {existing.npi} 已注册为 '{existing.name}'，与请求的 '{provider_data['name']}' 不符",
        )
    return existing


def _resolve_patient(patient_data):
    mrn = patient_data['mrn']
    name = patient_data['name']
    dob = patient_data['dob']

    try:
        existing = Patient.objects.get(mrn=mrn)
    except Patient.DoesNotExist:
        existing = None

    if existing is not None:
        if Patient.objects.filter(mrn=mrn, name=name, dob=dob).exists():
            return existing
        raise WarningException(
            code='PATIENT_MRN_MISMATCH',
            message=f"MRN {mrn} 已存在，但姓名或生日不匹配",
            detail={'existing': {'name': existing.name, 'dob': str(existing.dob)},
                    'requested': {'name': name, 'dob': str(dob)}},
        )

    try:
        conflicting = Patient.objects.get(name=name, dob=dob)
        raise WarningException(
            code='PATIENT_IDENTITY_CONFLICT',
            message=f"患者 {name} / {dob} 已存在，但 MRN 不同",
            detail={'existing_mrn': conflicting.mrn, 'requested_mrn': mrn},
        )
    except Patient.DoesNotExist:
        pass

    return Patient.objects.create(mrn=mrn, name=name, dob=dob)


def _check_duplicate_order(patient, medication, confirm):
    today = date.today()

    if Order.objects.filter(patient=patient, medication=medication, created_at__date=today).exists():
        raise BlockError(
            code='ORDER_SAME_DAY_DUPLICATE',
            message=f"患者 {patient.name} 今天已有 '{medication}' 的 order，不能重复提交",
        )

    if not confirm and Order.objects.filter(patient=patient, medication=medication).exists():
        raise WarningException(
            code='ORDER_HISTORY_DUPLICATE',
            message=f"患者 {patient.name} 历史上已有 '{medication}' 的 order",
            detail={'hint': '如需继续请在请求中加 confirm=true'},
        )


def create_care_plan(patient_data, provider_data, order_data, confirm=False):
    print("\n[2b] SERVICE 入口 - patient_data:", patient_data)

    provider = _resolve_provider(provider_data)
    patient = _resolve_patient(patient_data)
    _check_duplicate_order(patient, order_data['medication'], confirm)

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=order_data['medication'],
        diagnosis=order_data['diagnosis'],
        medical_record=order_data['medical_record'],
    )

    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )
    logger.info("已写入 DB：CarePlan #%d (status=pending)", care_plan.id)

    generate_care_plan.delay(care_plan.id)
    logger.info("已派发 Celery 任务：care_plan_id=%d", care_plan.id)

    return care_plan


def get_care_plan_event_stream(care_plan_id):
    r = redis_lib.Redis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()

    # 必须先 subscribe，再查 DB，防止竞态：
    # 如果先查 DB(pending) 再 subscribe，worker 可能刚好在这中间 publish，消息就丢了
    pubsub.subscribe(f"careplan:{care_plan_id}")

    try:
        care_plan = CarePlan.objects.get(pk=care_plan_id)
        if care_plan.status in (CarePlan.Status.COMPLETED, CarePlan.Status.FAILED):
            payload = {"status": care_plan.status}
            if care_plan.status == CarePlan.Status.COMPLETED:
                payload["content"] = care_plan.content
            yield f"data: {json.dumps(payload)}\n\n"
            return

        # 等待 Redis Pub/Sub 消息，最多等 5 分钟
        deadline = time.time() + 300
        while time.time() < deadline:
            # get_message(timeout=15)：最多阻塞 15 秒，没消息返回 None
            message = pubsub.get_message(timeout=15)
            if message and message["type"] == "message":
                yield f"data: {message['data'].decode()}\n\n"
                return
            # 每 15 秒发一个 SSE 注释行，防止代理/浏览器因超时断开连接
            yield ": heartbeat\n\n"

        # 超时：通知前端，让它自行处理（比如提示用户刷新）
        yield f"data: {json.dumps({'status': 'timeout'})}\n\n"

    finally:
        # 无论正常退出还是异常，都要清理 Redis 连接
        pubsub.unsubscribe()
        pubsub.close()
        r.close()


def list_care_plans_by_mrn(mrn):
    return (
        CarePlan.objects
        .filter(order__patient__mrn=mrn)
        .select_related('order__patient', 'order__provider')
        .order_by('-created_at')
    )
