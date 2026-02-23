# development.py
from .base import *


DEBUG = True

if DEBUG:
    import bonus.private as private

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-()h3p3y3z(&$8p5c7qym4b04oga7)&mu3160-qe^9f@qsa48h='

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'pa_bonus_db',
        'USER': 'postgres',
        'PASSWORD': private.db_pass,
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Email settings - use console backend for dev
# if DEBUG:
#     EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# else:
#     EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = private.email_host
EMAIL_PORT = private.smtp_port
EMAIL_USE_SSL = True
EMAIL_HOST_USER = private.smtp_login
EMAIL_HOST_PASSWORD = private.smtp_pass
DEFAULT_FROM_EMAIL = f'Bonusový Program <{private.smtp_login}>'

# DJANGO Q FOR ASYNC TASKS
Q_CLUSTER = {
    'name': 'bonus',
    'workers': 4,
    'recycle': 500,
    'timeout': 60,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Django Q2',
    'redis': {
        'host': 'localhost',
        'port': 6379,
        'db': 0,
    }
}