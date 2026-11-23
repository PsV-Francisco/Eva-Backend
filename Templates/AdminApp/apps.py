from django.apps import AppConfig


class AdminappConfig(AppConfig):
    name = 'AdminApp'

    def ready(self):
        from AdminApp import checks, signals  # noqa: F401
