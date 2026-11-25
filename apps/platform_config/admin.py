from django.contrib import admin

from apps.accounts.admin import ReadOnlyAdmin

from .models import ConfigAuditLog, ConfigSnapshot, SiteConfig


class SingletonAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteConfig)
class SiteConfigAdmin(SingletonAdmin):
    pass


@admin.register(ConfigAuditLog)
class ConfigAuditLogAdmin(ReadOnlyAdmin):  # entries cannot be edited or deleted (AC-09.11.3)
    list_display = ("at", "by", "action", "target_model", "target_id", "detail")
    list_filter = ("target_model",)
    search_fields = ("action", "detail", "target_id")


@admin.register(ConfigSnapshot)
class ConfigSnapshotAdmin(ReadOnlyAdmin):
    list_display = ("label", "taken_at", "taken_by")
