# production.py
import json
import os
from .base import *

SILENCED_SYSTEM_CHECKS = ['models.W037']

DEBUG = False
SECRET_KEY = os.getenv('SECRET_KEY')

ALLOWED_HOSTS = ['iepgvjxg.a2hosted.com', 'www.iepgvjxg.a2hosted.com', 
                 'bonuspl.iepgvjxg.a2hosted.com', 'bonuspl.ffhh.cz', 'www.bonuspl.ffhh.cz',
                 'bonus.primavera-and.pl', 'www.bonus.primavera-and.pl']


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USERNAME'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'sql_mode': 'STRICT_TRANS_TABLES',
        }
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

# Adjust SESSION cookie path so it doesn't interfere with other projects on the same domain
SESSION_COOKIE_PATH = '/bonuspl/'
CSRF_COOKIE_PATH = '/bonuspl/'

# CSRF must know the full origin
CSRF_TRUSTED_ORIGINS = [
    'https://primavera-and.pl',
    'https://www.primavera-and.pl',
    'https://iepgvjxg.a2hosted.com',
]

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
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': str(BASE_DIR / 'logs' / 'django_error.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'ERROR',
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'pa_bonus': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# --- STATIC & MEDIA: relative to BASE_DIR, self-contained ---
# BASE_DIR resolves to the project root (where manage.py lives)
# This keeps everything INSIDE the project directory, no more escaping to public_html

STATIC_URL = '/static_bonuspl/'
STATIC_ROOT = '/home/iepgvjxg/public_html/static_bonuspl/'

MEDIA_URL = '/media_bonuspl/'
MEDIA_ROOT = '/home/iepgvjxg/public_html/media_bonuspl/'
