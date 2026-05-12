import logging

import anthropic
from celery import shared_task

from .models import CarePlan

logger = logging.getLogger(__name__)


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
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": _build_prompt(care_plan.order)}],
        )
        care_plan.content = response.content[0].text
        care_plan.status = CarePlan.Status.COMPLETED
        care_plan.save(update_fields=["content", "status", "updated_at"])
        logger.info("CarePlan #%d → completed", care_plan_id)

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
