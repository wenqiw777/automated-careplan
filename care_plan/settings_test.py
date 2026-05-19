"""
测试专用 settings：
- SQLite in-memory 代替 Postgres → 不需要外部数据库，速度快
- Celery eager mode → task.delay() 同步执行，不需要 Redis/Worker
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
