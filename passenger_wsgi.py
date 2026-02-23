import os
import sys

path = '/home/iepgvjxg/bonus' # Absolute path
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'bonus.settings.production'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()