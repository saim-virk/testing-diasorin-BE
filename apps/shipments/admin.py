from django.contrib import admin

from apps.accounts.admin import ReadOnlyAdmin

from .models import (
    ApprovalRound,
    Attachment,
    Parcel,
    ReferenceCounter,
    RequestEvent,
    RequestLine,
    ShipmentRequest,
)


class LineInline(admin.TabularInline):
    model = RequestLine
    extra = 0


class ParcelInline(admin.TabularInline):
    model = Parcel
    extra = 0


@admin.register(ShipmentRequest)
class ShipmentRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "status",
        "requester",
        "destination",
        "consignee_company",
        "cost_centre_code",
        "created_at",
    )
    list_filter = ("status", "destination")
    search_fields = ("reference", "consignee_company", "cost_centre_code", "requester__email")
    inlines = [LineInline, ParcelInline]

    def has_delete_permission(self, request, obj=None):
        return False  # requests are cancelled, never deleted


@admin.register(RequestLine)
class RequestLineAdmin(admin.ModelAdmin):
    list_display = ("request", "position", "pvari_code", "description", "quantity", "temperature")
    search_fields = ("request__reference", "description", "pvari_code")


@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ("request", "position", "count", "packaging_code", "gross_weight_kg")


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("request", "kind", "original_name", "size_bytes", "uploaded_by", "uploaded_at")
    list_filter = ("kind",)


@admin.register(ApprovalRound)
class ApprovalRoundAdmin(admin.ModelAdmin):
    list_display = ("request", "round_number", "state", "required", "skip_reason", "started_at", "decided_by")
    list_filter = ("state", "required")
    search_fields = ("request__reference",)


@admin.register(RequestEvent)
class RequestEventAdmin(ReadOnlyAdmin):
    list_display = ("request", "at", "actor", "actor_role", "kind", "in_conversation", "action", "to_status")
    list_filter = ("kind", "in_conversation", "action", "actor_role")
    search_fields = ("request__reference", "note")


@admin.register(ReferenceCounter)
class ReferenceCounterAdmin(admin.ModelAdmin):
    list_display = ("year", "last_number")
