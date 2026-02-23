"""
ASGI config for bonus project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bonus.settings.development')
# Check for "production" and load settings if found
if os.environ.get('DJANGO_ENVIRONMENT') == 'production':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bonus.settings.production'


application = get_asgi_application()
