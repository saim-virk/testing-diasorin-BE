from django.contrib import admin

from .models import (
    Branch,
    Carrier,
    CostCentre,
    CostCentreApprover,
    Country,
    PackagingType,
    PVARICode,
    ReasonCode,
    ShipsFromSite,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("iso2", "name", "scope", "is_active")
    list_filter = ("scope", "is_active")
    search_fields = ("iso2", "name")


@admin.register(PVARICode)
class PVARICodeAdmin(admin.ModelAdmin):
    list_display = ("code", "un_number", "description_en", "hazard", "default_temperature", "is_active")
    list_filter = ("hazard", "default_temperature", "is_active")
    search_fields = ("code", "description_en", "description_it")


@admin.register(ReasonCode)
class ReasonCodeAdmin(admin.ModelAdmin):
    list_display = ("scope_group", "code", "description_en", "description_it", "is_active")
    list_filter = ("scope_group", "is_active")
    search_fields = ("code", "description_en", "description_it")


@admin.register(ShipsFromSite)
class ShipsFromSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "applies_calendar", "allowed_weekdays", "is_active")


@admin.register(PackagingType)
class PackagingTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "dimensions", "description", "is_active")
    search_fields = ("code",)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scope", "country", "po_required", "is_active")
    list_filter = ("scope", "is_active")
    search_fields = ("code", "name")


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")


class ApproverInline(admin.TabularInline):
    model = CostCentreApprover
    extra = 0
    autocomplete_fields = ("user",)
    exclude = ("added_by",)


@admin.register(CostCentre)
class CostCentreAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "approval_required", "is_active")
    list_filter = ("approval_required", "is_active")
    search_fields = ("code", "name")
    inlines = [ApproverInline]


@admin.register(CostCentreApprover)
class CostCentreApproverAdmin(admin.ModelAdmin):
    list_display = ("cost_centre", "user", "added_at")
    search_fields = ("cost_centre__code", "user__email")
