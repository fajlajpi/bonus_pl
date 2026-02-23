# production.py
import json
import os
from .base import *

DEBUG = False
SECRET_KEY = os.getenv('SECRET_KEY')

ALLOWED_HOSTS = ['bonus.primavera-and.cz', 'www.bonus.primavera-and.cz', 
                 'iepgvjxg.a2hosted.com', 'www.iepgvjxg.a2hosted.com', 
                 'bonus.ffhh.cz', 'www.bonus.ffhh.cz', 'bonus.iepgvjxg.a2hosted.com']

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USERNAME'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
    }
}

# I18N and TZ
LANGUAGE_CODE = 'cs'
TIME_ZONE = 'Europe/Prague'


# Email settings for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.example.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '465'))
EMAIL_USE_SSL = True
EMAIL_HOST_USER = os.environ.get('EMAIL_USER', 'user@example.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'password')
DEFAULT_FROM_EMAIL = f'Bonusový Program <{EMAIL_HOST_USER}>'

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Django Q settings - adjust workers based on server capacity
Q_CLUSTER = {
    'name': 'bonus',
    'workers': 2,
    'recycle': 500,
    'timeout': 60,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Django Q2',
    'redis': {
        'host': os.environ.get('REDIS_HOST', 'localhost'),
        'port': 6379,
        'db': 0,
    }
}

# Increase logging severity for production
# LOGGING['loggers']['pa_bonus']['level'] = 'WARNING'
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': '/home/iepgvjxg/public_html/logs/django_error.log',
            'formatter': 'verbose',
        },
        'debug_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/home/iepgvjxg/public_html/logs/django_debug.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'ERROR',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'debug_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'pa_bonus': {
            'handlers': ['file', 'debug_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'pa_bonus.tasks': {
            'handlers': ['file', 'debug_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = '/home/iepgvjxg/public_html/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = '/home/iepgvjxg/public_html/media/'