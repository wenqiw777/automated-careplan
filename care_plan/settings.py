import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CAREPLAN_QUEUE_NAME = 'careplan_tasks'

SECRET_KEY = 'dev-only-not-for-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'care_plan',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'careplan',
        'USER': 'careplan',
        'PASSWORD': 'careplan',
        'HOST': 'db',
        'PORT': '5432',
    }
}

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'care_plan.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
    },
]

WSGI_APPLICATION = 'care_plan.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
