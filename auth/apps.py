from django.apps import AppConfig


class AuthConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'auth'
    label = 'user_auth'

    def ready(self):
        from . import signals  # noqa: F401
