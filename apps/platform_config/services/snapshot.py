"""Go-live configuration snapshot (DSF-09.12). Only the capture lives here; the reset is day 6."""

from django.forms.models import model_to_dict

from apps.accounts.models import AllowedDomain, AllowedEmail, BlockedEmail, RoleAssignment, User
from apps.masterdata.models import (
    Branch,
    Carrier,
    CostCentre,
    CostCentreApprover,
    PackagingType,
    ReasonCode,
    ShipsFromSite,
)
from apps.notifications.models import EmailTemplate

from ..models import ConfigSnapshot, SiteConfig


def _rows(qs, *fields: str) -> list[dict]:
    return [model_to_dict(obj, fields=list(fields)) for obj in qs]


def build_snapshot_data() -> dict:
    """Everything the reset must be able to restore, keyed by natural keys (codes, emails)."""
    return {
        "access": {
            "allowed_domains": _rows(AllowedDomain.objects.all(), "domain"),
            "allowed_emails": _rows(AllowedEmail.objects.all(), "email", "note"),
            "blocked_emails": _rows(BlockedEmail.objects.all(), "email", "reason"),
            "role_assignments": [
                {"email": r.user.email, "role": r.role} for r in RoleAssignment.objects.select_related("user")
            ],
            "approval_exempt_emails": list(
                User.objects.filter(approval_exempt=True).order_by("email").values_list("email", flat=True)
            ),
        },
        "cost_centres": [
            {
                **model_to_dict(cc, fields=["code", "name", "approval_required", "is_active"]),
                "approvers": sorted(
                    CostCentreApprover.objects.filter(cost_centre=cc).values_list("user__email", flat=True)
                ),
            }
            for cc in CostCentre.objects.all()
        ],
        "site_config": model_to_dict(SiteConfig.load(), exclude=["id"]),  # approval rules, SLA, sync, ...
        "email_templates": _rows(EmailTemplate.objects.all(), "key", "enabled"),
        "branches": [
            {
                **model_to_dict(b, fields=["code", "name", "scope", "is_active"]),
                "country": b.country.iso2 if b.country else None,
            }
            for b in Branch.objects.select_related("country")
        ],
        "reason_codes": _rows(
            ReasonCode.objects.all(), "scope_group", "code", "description_it", "description_en", "is_active"
        ),
        "packaging_types": _rows(
            PackagingType.objects.all(), "code", "dimensions", "description", "is_active"
        ),
        "carriers": _rows(Carrier.objects.all(), "name", "is_active"),
        "ships_from_sites": _rows(
            ShipsFromSite.objects.all(), "code", "name", "applies_calendar", "allowed_weekdays", "is_active"
        ),
    }


def take_snapshot(label: str, by: User | None = None) -> ConfigSnapshot:
    return ConfigSnapshot.objects.create(label=label, taken_by=by, data=build_snapshot_data())
