from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from django.contrib import admin

        from . import signals  # noqa: F401
        from .admin_login import admin_login

        # Administrators reach Django Admin through their normal one-time-code session: no password form.
        admin.site.login = admin_login
