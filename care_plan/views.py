import json
import logging
import time

import redis as redis_lib
from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import CarePlan, Order, Patient, Provider
from .tasks import generate_care_plan

logger = logging.getLogger(__name__)


def form_view(request):
    return render(request, 'form.html')


def submit_view(request):
    full_name = (
        f"{request.POST.get('patient_first_name', '').strip()} "
        f"{request.POST.get('patient_last_name', '').strip()}"
    ).strip()

    patient, _ = Patient.objects.get_or_create(
        mrn=request.POST.get('patient_mrn', ''),
        defaults={
            'name': full_name,
            'dob': request.POST.get('patient_dob') or None,
        },
    )

    provider, _ = Provider.objects.get_or_create(
        npi=request.POST.get('provider_npi', ''),
        defaults={'name': request.POST.get('provider_name', '')},
    )

    diagnosis = request.POST.get('primary_diagnosis', '')
    if request.POST.get('additional_diagnoses'):
        diagnosis = f"{diagnosis}; {request.POST.get('additional_diagnoses')}"

    medical_record_parts = []
    if request.POST.get('medication_history'):
        medical_record_parts.append(f"Medication history: {request.POST.get('medication_history')}")
    if request.POST.get('patient_records'):
        medical_record_parts.append(f"Records: {request.POST.get('patient_records')}")

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=request.POST.get('medication_name', ''),
        diagnosis=diagnosis,
        medical_record="\n\n".join(medical_record_parts),
    )

    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )

    logger.info("已写入 DB：CarePlan #%d (status=pending)", care_plan.id)

    generate_care_plan.delay(care_plan.id)
    logger.info("已派发 Celery 任务：care_plan_id=%d", care_plan.id)

    return redirect('care_plan_detail', care_plan_id=care_plan.id)


def care_plan_detail(request, care_plan_id):
    care_plan = get_object_or_404(
        CarePlan.objects.select_related('order__patient', 'order__provider'),
        pk=care_plan_id,
    )
    return render(request, 'result.html', {'care_plan': care_plan})


def download_care_plan(request, care_plan_id):
    care_plan = get_object_or_404(CarePlan, pk=care_plan_id)
    content = care_plan.content or '(care plan still being generated)'
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="care_plan_{care_plan_id}.txt"'
    return response


def care_plan_sse(request, care_plan_id):
    """
    长连接：浏览器连上来后，这个 view 会一直挂着，直到 Celery 发来结果。
    用 StreamingHttpResponse + generator 实现——generator yield 一行，浏览器就收到一行。
    """
    def event_stream():
        r = redis_lib.Redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()

        # 必须先 subscribe，再查 DB，防止竞态：
        # 如果先查 DB(pending) 再 subscribe，worker 可能刚好在这中间 publish，消息就丢了
        pubsub.subscribe(f"careplan:{care_plan_id}")

        try:
            # 如果连上来时任务已经跑完，直接返回，不用等
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
                    # message["data"] 是 bytes，decode 成字符串
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

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # 告诉 Nginx 不要缓冲，立即透传给浏览器
    return response


def care_plan_status(request, care_plan_id):
    """轮询用：只返回 status 和（完成时的）content，不渲染整页 HTML。"""
    care_plan = get_object_or_404(CarePlan, pk=care_plan_id)
    data = {'status': care_plan.status}
    # content 只在 completed 时有意义，避免把空字符串传给前端
    if care_plan.status == CarePlan.Status.COMPLETED:
        data['content'] = care_plan.content
    return JsonResponse(data)


def get_care_plans_by_mrn(request):
    mrn = request.GET.get('mrn', '')
    if mrn == '':
        return JsonResponse({'error': 'MRN is required'}, status=400)

    care_plans = (
        CarePlan.objects
        .filter(order__patient__mrn=mrn)
        .select_related('order__patient', 'order__provider')
        .order_by('-created_at')
    )

    result = [
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
    return JsonResponse({'care_plans': result})
