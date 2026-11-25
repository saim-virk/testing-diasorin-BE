"""Data model v2 migrations move the data (run last: it flushes the database when done)."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [
    ("accounts", "0004_user_language"),
    ("platform_config", "0002_seed_singletons"),
    ("masterdata", "0002_seed_reference_data"),
    ("notifications", "0002_seed_email_templates"),
    ("shipments", "0001_initial"),
    ("inventory", "0001_initial"),
]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_v2_migrations_move_calendar_exemptions_sync_settings_and_comments():
    try:
        old = _migrate(BEFORE)

        # --- old shape
        User = old.get_model("accounts", "User")
        u = User.objects.create(email="exempt@diasorin.com", last_login_at="2026-01-02T03:04:05Z")
        other = User.objects.create(email="normal@diasorin.com")
        old.get_model("platform_config", "ApprovalExemption").objects.create(user=u)
        sync, _ = old.get_model("platform_config", "SyncConfig").objects.get_or_create(pk=1)
        sync.host, sync.path, sync.pattern = "sftp.example", "/in/", "stock_*.csv"
        sync.every_minutes, sync.alert_hours, sync.on_missing = 7, 9, "keep"
        sync.notify_admins = False
        sync.save()
        Site = old.get_model("masterdata", "ShipsFromSite")
        Day = old.get_model("masterdata", "ShippingCalendarDay")
        saluggia = Site.objects.get(code="SALUGGIA")
        for weekday in range(7):  # going back recreates the table empty: fill it like the old seed did
            Day.objects.create(site=saluggia, weekday=weekday, allowed=weekday < 4)
        Request = old.get_model("shipments", "ShipmentRequest")
        req = Request.objects.create(reference="SR-1", requester=u, applicant_email=u.email)
        old.get_model("shipments", "RawMaterialDetail").objects.create(
            request=req, description="Protein A", lot_number="L1", number_of_vials=4
        )
        old.get_model("shipments", "USRequirements").objects.create(
            request=req, usda_permit="YES", cdc_permit="NO"
        )
        old.get_model("shipments", "Comment").objects.create(
            request=req, author=u, author_role="approver", kind="REJECTED", text="No budget"
        )
        old.get_model("shipments", "Comment").objects.create(
            request=req, author=u, author_role="requester", kind="QUESTION", text="Why?"
        )
        old.get_model("shipments", "RequestEvent").objects.create(request=req, action="created")
        assert Site.objects.get(code="GERENZANO").pk

        # --- forward to the latest state
        new = _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

        NewUser = new.get_model("accounts", "User")
        assert NewUser.objects.get(email="exempt@diasorin.com").approval_exempt is True
        assert NewUser.objects.get(email="normal@diasorin.com").approval_exempt is False
        assert NewUser.objects.get(email="exempt@diasorin.com").last_login is not None
        assert other.pk

        site = new.get_model("platform_config", "SiteConfig").objects.get(pk=1)
        assert (site.sync_host, site.sync_path, site.sync_pattern) == ("sftp.example", "/in/", "stock_*.csv")
        assert (site.sync_every_minutes, site.sync_alert_hours) == (7, 9)
        assert site.sync_on_missing == "keep" and site.sync_notify_admins is False

        NewSite = new.get_model("masterdata", "ShipsFromSite")
        assert NewSite.objects.get(code="SALUGGIA").allowed_weekdays == [0, 1, 2, 3]
        assert NewSite.objects.get(code="GERENZANO").allowed_weekdays == []

        r = new.get_model("shipments", "ShipmentRequest").objects.get(reference="SR-1")
        assert (r.rm_description, r.rm_lot_number, r.rm_number_of_vials) == ("Protein A", "L1", 4)
        assert (r.us_usda_permit, r.us_cdc_permit) == ("YES", "NO")
        events = new.get_model("shipments", "RequestEvent").objects.filter(request=r)
        assert events.count() == 3
        rejected = events.get(action="rejected")
        assert rejected.in_conversation and rejected.note == "No budget" and rejected.kind == "EVENT"
        question = events.get(kind="QUESTION")
        assert question.in_conversation and question.note == "Why?"
        assert not events.get(action="created").in_conversation
    finally:
        call_command("migrate", verbosity=0)  # leave the schema at the latest state


@pytest.mark.django_db
def test_no_model_changes_are_missing_a_migration():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)
