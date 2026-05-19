"""
测试专用 settings：
- 本地：SQLite in-memory → 不需要外部数据库，速度快
- CI：PostgreSQL → 和生产环境一致，能 catch 到数据库差异的 bug
- Celery eager mode → task.delay() 同步执行，不需要 Redis/Worker
"""
import os

from .settings import *  # noqa: F401,F403

if os.environ.get('CI'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'careplan_test',
            'USER': 'careplan',
            'PASSWORD': 'careplan',
            'HOST': 'localhost',
            'PORT': '5432',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
