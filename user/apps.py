from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'

    def ready(self):
        # Import signal handlers to ensure they're registered when the app is ready
        try:
            import user.signals  # noqa: F401
        except Exception:
            # Avoid raising on import errors during some management commands
            pass
