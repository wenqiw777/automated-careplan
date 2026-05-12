# 让 Django 启动时就加载 Celery app，确保 @shared_task 能找到它
from .celery import app as celery_app

__all__ = ["celery_app"]
