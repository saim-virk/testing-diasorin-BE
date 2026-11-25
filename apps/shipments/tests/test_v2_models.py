import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.platform_config.models import ConfigAuditLog
from apps.shipments.models import ApprovalRound, RequestEvent, ShipmentRequest

pytestmark = pytest.mark.django_db


@pytest.fixture
def request_row(make_user):
    user = make_user("req@diasorin.com")
    return ShipmentRequest.objects.create(
        reference="SR-2026-0001", requester=user, applicant_email=user.email
    )


def test_second_pending_round_is_refused_by_the_database(request_row):
    ApprovalRound.objects.create(request=request_row, round_number=1, state="PENDING")
    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovalRound.objects.create(request=request_row, round_number=2, state="PENDING")


def test_a_held_round_is_open_too(request_row):
    ApprovalRound.objects.create(request=request_row, round_number=1, state="HELD")
    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovalRound.objects.create(request=request_row, round_number=2, state="PENDING")
    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovalRound.objects.create(request=request_row, round_number=2, state="HELD")


def test_closed_rounds_do_not_block_a_new_open_one(request_row):
    ApprovalRound.objects.create(request=request_row, round_number=1, state="REJECTED")
    ApprovalRound.objects.create(request=request_row, round_number=2, state="SUPERSEDED")
    ApprovalRound.objects.create(request=request_row, round_number=3, state="PENDING")


def test_deleting_a_request_with_events_is_refused(request_row):
    RequestEvent.objects.create(request=request_row, action="created")
    with pytest.raises(ProtectedError):
        request_row.delete()


def test_a_decision_is_one_event_with_the_reason_in_the_note(request_row):
    ev = RequestEvent.objects.create(
        request=request_row,
        action="rejected",
        kind="EVENT",
        in_conversation=True,
        actor_role="approver",
        note="Wrong cost centre. " * 40,  # longer than the old 500-char limit
    )
    assert RequestEvent.objects.filter(request=request_row, in_conversation=True).get() == ev
    assert len(ev.note) > 500


def test_admin_offers_no_delete_for_requests_events_audit_or_users(rf, make_user):
    req = rf.get("/")
    req.user = make_user("ad@diasorin.com", admin=True)
    for model in (ShipmentRequest, RequestEvent, ConfigAuditLog, User):
        assert admin.site._registry[model].has_delete_permission(req) is False, model
    for model in (RequestEvent, ConfigAuditLog):  # events and audit rows are not editable either
        assert admin.site._registry[model].has_change_permission(req) is False, model
