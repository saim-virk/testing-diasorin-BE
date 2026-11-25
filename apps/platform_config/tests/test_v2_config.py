from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.masterdata.models import CostCentre, CostCentreApprover
from apps.platform_config.models import ConfigAuditLog, ConfigSnapshot
from apps.platform_config.services.audit import PUBLISHED_ACTION, unpublished_changes_count

pytestmark = pytest.mark.django_db


def _log(action, minutes):
    return ConfigAuditLog.objects.create(action=action, at=timezone.now() + timedelta(minutes=minutes))


def test_unpublished_changes_count_counts_rows_since_the_last_publish():
    assert unpublished_changes_count() == 0
    _log("cost_centre_updated", 1)
    _log("rule_updated", 2)
    assert unpublished_changes_count() == 2  # never published: everything counts
    _log(PUBLISHED_ACTION, 3)
    assert unpublished_changes_count() == 0
    _log("rule_updated", 4)
    _log("approver_added", 5)
    _log("approver_removed", 6)
    assert unpublished_changes_count() == 3
    _log(PUBLISHED_ACTION, 7)
    assert unpublished_changes_count() == 0


def test_take_golive_snapshot_writes_one_snapshot_with_every_section(make_user):
    approver = make_user("ap@diasorin.com")
    cc = CostCentre.objects.create(code="CC-9", name="Nine")
    CostCentreApprover.objects.create(cost_centre=cc, user=approver)
    make_user("ex@diasorin.com", approval_exempt=True)

    call_command("take_golive_snapshot", "--label", "go-live")

    snap = ConfigSnapshot.objects.get()
    assert snap.label == "go-live"
    data = snap.data
    assert {
        "access",
        "cost_centres",
        "site_config",
        "email_templates",
        "branches",
        "reason_codes",
        "packaging_types",
        "carriers",
        "ships_from_sites",
    } <= set(data)
    assert {"allowed_domains", "allowed_emails", "blocked_emails", "role_assignments"} <= set(data["access"])
    assert data["access"]["approval_exempt_emails"] == ["ex@diasorin.com"]
    assert data["cost_centres"][0]["approvers"] == ["ap@diasorin.com"]
    assert data["site_config"]["sla_hours"] == 24 and "sync_path" in data["site_config"]
    assert len(data["email_templates"]) == 17
    assert len(data["reason_codes"]) == 22 and len(data["carriers"]) == 5
    saluggia = next(s for s in data["ships_from_sites"] if s["code"] == "SALUGGIA")
    assert saluggia["allowed_weekdays"] == [0, 1, 2, 3]
