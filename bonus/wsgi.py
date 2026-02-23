"""
WSGI config for bonus project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bonus.settings.development')
# Check for "production" and load settings if found
if os.environ.get('DJANGO_ENVIRONMENT') == 'production':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bonus.settings.production'

application = get_wsgi_application()
