import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.accounts.models import AllowedDomain, User
from apps.masterdata.models import Branch, CostCentre, CostCentreApprover
from apps.platform_config.models import SiteConfig

pytestmark = pytest.mark.django_db


def test_siteconfig_singleton():
    cfg = SiteConfig.load()
    assert cfg.pk == 1
    assert cfg.otp_minutes == 10
    assert cfg.session_idle_minutes == 30
    assert cfg.no_approver_fallback == "ADMIN"
    assert cfg.sender_email == "noreply-shipments@diasorin.com"
    assert cfg.ticketing_url == ""
    with pytest.raises(IntegrityError), transaction.atomic():
        SiteConfig.objects.create()
    assert SiteConfig.objects.count() == 1


def test_sync_settings_live_on_site_config_with_defaults():
    cfg = SiteConfig.load()
    assert (cfg.sync_path, cfg.sync_pattern, cfg.sync_every_minutes) == (
        "/inventory/outbound/",
        "inventory_*.csv",
        15,
    )
    assert cfg.sync_on_missing == "deactivate" and cfg.sync_notify_admins is True


def test_allowed_domains_seeded():
    assert set(AllowedDomain.objects.values_list("domain", flat=True)) == {
        "diasorin.com",
        "diasorin.it",
        "diasorin-inc.com",
    }


def test_seed_demo_is_idempotent():
    call_command("seed_demo", "--with-requests")
    snapshot = (
        User.objects.count(),
        CostCentre.objects.count(),
        Branch.objects.count(),
        CostCentreApprover.objects.count(),
    )
    call_command("seed_demo")
    assert (
        User.objects.count(),
        CostCentre.objects.count(),
        Branch.objects.count(),
        CostCentreApprover.objects.count(),
    ) == snapshot
    assert snapshot == (10, 6, 11, 6)
    admin = User.objects.get(email="admin@diasorin.com")
    assert admin.is_staff
    assert admin.role_assignments.filter(role="admin").exists()


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": True}


PUBLIC_KEYS = {
    "ticketing_url", "sla_hours", "reminder_hours", "escalate_hours", "approval_global_enabled",
    "no_approver_fallback", "reject_comment_required", "self_approval_mode", "po_mandatory_us", "msds_required_other_hazard", "max_parcel_lines",
    "sync_path", "sync_pattern", "sync_every_minutes", "sync_alert_hours", "sync_archive_path",
}  # fmt: skip


def test_public_site_endpoint_anonymous_and_complete(client):
    body = client.get("/api/public/site").json()
    assert set(body) == PUBLIC_KEYS
    assert body["ticketing_url"] == ""
    assert (body["sla_hours"], body["reminder_hours"], body["escalate_hours"]) == (24, 24, 48)
    assert body["sync_path"] == "/inventory/outbound/" and body["sync_every_minutes"] == 15


def test_self_approval_mode_defaults_to_route_to_others_and_the_old_flag_is_gone():
    cfg = SiteConfig.load()
    assert cfg.self_approval_mode == "ROUTE_TO_OTHERS"
    assert not hasattr(cfg, "block_self_approval")


def test_public_site_reflects_config_changes_immediately(client):
    cfg = SiteConfig.load()
    cfg.ticketing_url = "https://tickets.example.com"
    cfg.sla_hours, cfg.reminder_hours, cfg.escalate_hours = 12, 6, 30
    cfg.self_approval_mode = "AUTO_APPROVE"
    cfg.save()
    cfg.sync_path, cfg.sync_pattern = "/x/", "stock_*.csv"
    cfg.sync_every_minutes, cfg.sync_alert_hours, cfg.sync_archive_path = 5, 3, "/done/"
    cfg.save()
    body = client.get("/api/public/site").json()
    assert body["ticketing_url"] == "https://tickets.example.com"
    assert (body["sla_hours"], body["reminder_hours"], body["escalate_hours"]) == (12, 6, 30)
    assert body["self_approval_mode"] == "AUTO_APPROVE"
    assert (body["sync_path"], body["sync_pattern"], body["sync_every_minutes"]) == ("/x/", "stock_*.csv", 5)
    assert (body["sync_alert_hours"], body["sync_archive_path"]) == (3, "/done/")


def test_public_site_never_exposes_the_sftp_host(client):
    cfg = SiteConfig.load()
    cfg.sync_host = "sftp.secret-host.internal"
    cfg.save()
    raw = client.get("/api/public/site").content.decode()
    assert "secret-host" not in raw and "host" not in raw.lower()


def test_cost_centres_endpoint_needs_sign_in_and_lists_active(api, make_user, sign_in):
    CostCentre.objects.create(code="CC-1", name="One", approval_required=True)
    CostCentre.objects.create(code="CC-2", name="Two", approval_required=False)
    CostCentre.objects.create(code="CC-3", name="Old", is_active=False)
    assert api.get("/api/masterdata/cost-centres").status_code == 401
    make_user("m.rossi@diasorin.com")
    sign_in("m.rossi@diasorin.com")
    rows = api.get("/api/masterdata/cost-centres").json()
    assert [r["code"] for r in rows] == ["CC-1", "CC-2"]
    assert rows[0]["approval_hint"]["required"] is True
    assert rows[1]["approval_hint"] == {"required": False, "why": "cost_centre_off", "approvers": []}
