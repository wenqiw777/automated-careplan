import json
import logging
import os

import anthropic
import redis as redis_lib
from celery import shared_task
from django.conf import settings

from .models import CarePlan

logger = logging.getLogger(__name__)


def _publish(care_plan_id: int, payload: dict) -> None:
    """Celery worker 用这个函数通知 Django SSE view：任务结束了。"""
    r = redis_lib.Redis.from_url(settings.REDIS_URL)
    channel = f"careplan:{care_plan_id}"
    r.publish(channel, json.dumps(payload))
    logger.info("Published to Redis channel %s: %s", channel, payload.get("status"))


_MOCK_CARE_PLAN = """
SPECIALTY PHARMACY CARE PLAN [MOCK — development only]
=======================================================

MEDICATION PURPOSE
Adalimumab (Humira) is a TNF inhibitor used to reduce inflammation in
autoimmune conditions including rheumatoid arthritis and Crohn's disease.

DOSING INSTRUCTIONS
- Initial dose: 160 mg SC (four 40 mg injections in one day, or two injections/day for 2 days)
- Week 2: 80 mg SC
- Week 4 onward: 40 mg SC every other week
- Administer in abdomen, thigh, or upper arm; rotate injection sites.

MONITORING PARAMETERS
- CBC with differential every 3 months
- Hepatic function panel every 6 months
- TB screening (QuantiFERON) before initiation; annual reassessment
- Monitor for signs of infection at every visit

SIDE EFFECTS TO REPORT IMMEDIATELY
- Fever, chills, or persistent cough (infection risk)
- Numbness or tingling (rare neurological events)
- New or worsening heart failure symptoms

PATIENT EDUCATION
- Store pens refrigerated (2–8 °C); never freeze
- Allow pen to reach room temperature 15–30 min before injection
- Avoid live vaccines while on therapy
- Carry a medication alert card at all times

FOLLOW-UP SCHEDULE
- Week 2: Tolerability check (phone or portal)
- Week 4: In-clinic injection technique review
- Month 3: Lab review + efficacy assessment
- Every 6 months thereafter: Comprehensive medication management visit
""".strip()


def _call_llm(prompt: str) -> str:
    """
    LLM 调用的统一入口。
    USE_MOCK_LLM=true 时直接返回假数据，不消耗 API quota。
    """
    if os.environ.get("USE_MOCK_LLM", "false").lower() == "true":
        logger.info("Mock LLM enabled — skipping real API call")
        return _MOCK_CARE_PLAN

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _build_prompt(order) -> str:
    return f"""You are a specialty pharmacy clinical specialist.
Generate a structured care plan for the following patient.

Patient : {order.patient.name} (MRN: {order.patient.mrn})
Provider: {order.provider.name} (NPI: {order.provider.npi})
Medication : {order.medication}
Diagnosis  : {order.diagnosis}
Medical record:
{order.medical_record}

Include: medication purpose, dosing instructions, monitoring parameters,
side effects, patient education points, and follow-up schedule.
"""


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,   # 任务完成后才从队列删除，crash 了会重新入队
)
def generate_care_plan(self, care_plan_id: int) -> None:
    care_plan = CarePlan.objects.select_related(
        "order__patient", "order__provider"
    ).get(pk=care_plan_id)

    care_plan.status = CarePlan.Status.PROCESSING
    care_plan.save(update_fields=["status", "updated_at"])
    logger.info("CarePlan #%d → processing (attempt %d/3)", care_plan_id, self.request.retries + 1)

    try:
        care_plan.content = _call_llm(_build_prompt(care_plan.order))
        care_plan.status = CarePlan.Status.COMPLETED
        care_plan.save(update_fields=["content", "status", "updated_at"])
        logger.info("CarePlan #%d → completed", care_plan_id)

        # DB 已更新后，通知所有等待这个 care plan 的 SSE 连接
        _publish(care_plan_id, {"status": "completed", "content": care_plan.content})

    except Exception as exc:
        # 指数退避：第1次重试等30s，第2次60s，第3次120s
        countdown = 2 ** self.request.retries * 30
        logger.warning(
            "CarePlan #%d 第%d次失败，%ds 后重试：%s",
            care_plan_id, self.request.retries + 1, countdown, exc,
        )
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            care_plan.status = CarePlan.Status.FAILED
            care_plan.save(update_fields=["status", "updated_at"])
            logger.error("CarePlan #%d → failed，已重试 3 次放弃", care_plan_id)
            _publish(care_plan_id, {"status": "failed"})
