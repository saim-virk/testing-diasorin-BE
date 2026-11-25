from django.contrib import admin

from apps.accounts.admin import ReadOnlyAdmin

from .models import EmailOutbox, EmailTemplate

HIDDEN = "[hidden: sign-in email]"


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "recipients_description", "enabled")
    list_filter = ("enabled",)
    search_fields = ("key", "name", "subject_en")


@admin.register(EmailOutbox)
class EmailOutboxAdmin(ReadOnlyAdmin):
    """Sign-in (`otp`) rows never show subject or body: an admin must not be able to read a live code."""

    list_display = (
        "template_key",
        "to_addresses",
        "shown_subject",
        "status",
        "attempts",
        "created_at",
        "sent_at",
        "next_attempt_at",
    )
    list_filter = ("status", "template_key")
    search_fields = ("to_addresses", "dedupe_key")  # not subject/body: searching could reveal a code
    fields = (
        "template_key", "request", "to_addresses", "shown_subject", "shown_body", "status",
        "attempts", "last_error", "created_at", "sent_at", "next_attempt_at", "dedupe_key",
    )  # fmt: skip
    readonly_fields = fields

    @admin.display(description="subject")
    def shown_subject(self, obj):
        return HIDDEN if obj.template_key == "otp" else obj.subject

    @admin.display(description="body")
    def shown_body(self, obj):
        return HIDDEN if obj.template_key == "otp" else obj.body
