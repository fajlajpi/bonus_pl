#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""

    # Default to development settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bonus.settings.development')

    # Check for "production" and load settings if found
    if os.environ.get('DJANGO_ENVIRONMENT') == 'production':
        os.environ['DJANGO_SETTINGS_MODULE'] = 'bonus.settings.production'

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
