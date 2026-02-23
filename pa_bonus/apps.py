from django.apps import AppConfig


class PaBonusConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pa_bonus'

    def ready(self):
        import pa_bonus.signals  # Import signals when the app is ready
