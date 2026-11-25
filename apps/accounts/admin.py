from django.contrib import admin

from .models import (
    AllowedDomain,
    AllowedEmail,
    BlockedEmail,
    OTPChallenge,
    RoleAssignment,
    User,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """For immutable log / event models."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "department",
        "language",
        "is_active",
        "approval_exempt",
        "is_staff",
    )
    list_filter = ("is_active", "is_staff", "approval_exempt", "language")
    search_fields = ("email", "first_name", "last_name", "department")
    exclude = ("password",)

    def has_delete_permission(self, request, obj=None):
        return False  # users are deactivated, never deleted


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "added_by", "added_at")
    list_filter = ("role",)
    search_fields = ("user__email",)


@admin.register(AllowedDomain)
class AllowedDomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "added_by", "added_at")
    search_fields = ("domain",)


@admin.register(AllowedEmail)
class AllowedEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "note", "added_by", "added_at")
    search_fields = ("email", "note")


@admin.register(BlockedEmail)
class BlockedEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "reason", "added_by", "added_at")
    search_fields = ("email", "reason")


@admin.register(OTPChallenge)
class OTPChallengeAdmin(ReadOnlyAdmin):
    list_display = ("email", "created_at", "expires_at", "attempts", "consumed_at", "ip_address")
    search_fields = ("email",)
