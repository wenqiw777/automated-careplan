"""
Worker: 从 Redis 队列取任务 → 调 LLM → 把结果写回数据库。
这是一个独立进程，和 Django web server 完全分开跑。
"""

import json
import logging
import os

# Django 需要在 import models 之前初始化
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "care_plan.settings")

import django
django.setup()

import anthropic
import redis
from django.conf import settings

from care_plan.models import CarePlan

logger = logging.getLogger(__name__)


def build_prompt(order) -> str:
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


def process(care_plan_id: int) -> None:
    # 1. 从 DB 取出这条 CarePlan（顺带 join Order/Patient/Provider）
    care_plan = CarePlan.objects.select_related(
        "order__patient", "order__provider"
    ).get(pk=care_plan_id)

    # 2. 标记 processing，让用户刷新时能看到"正在生成"
    care_plan.status = CarePlan.Status.PROCESSING
    care_plan.save(update_fields=["status", "updated_at"])
    logger.info("CarePlan #%d → processing", care_plan_id)

    # 3. 调 LLM
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": build_prompt(care_plan.order)}],
    )

    # 4. 写回数据库
    care_plan.content = response.content[0].text
    care_plan.status = CarePlan.Status.COMPLETED
    care_plan.save(update_fields=["content", "status", "updated_at"])
    logger.info("CarePlan #%d → completed", care_plan_id)


def run() -> None:
    r = redis.Redis.from_url(settings.REDIS_URL)
    queue = settings.CAREPLAN_QUEUE_NAME
    logger.info("Worker started. Listening on [%s] ...", queue)

    while True:
        # BLPOP：有消息就立刻返回，没消息就一直阻塞（timeout=0）
        # 返回值是 (queue_name_bytes, message_bytes) 或 None（超时才会 None）
        result = r.blpop(queue, timeout=0)
        if result is None:
            continue

        _, raw = result
        data = json.loads(raw)
        care_plan_id = data["care_plan_id"]
        logger.info("Received task: care_plan_id=%d", care_plan_id)

        try:
            process(care_plan_id)
        except Exception as exc:
            logger.exception("Failed to process CarePlan #%d: %s", care_plan_id, exc)
            # 失败了也要更新状态，否则前端永远看到 processing
            CarePlan.objects.filter(pk=care_plan_id).update(
                status=CarePlan.Status.FAILED
            )


if __name__ == "__main__":
    run()
