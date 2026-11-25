"""Day 4 backend: approve / reject / return / cancel / reassign / skip, resubmission (DSF-04.04), visibility,
event visibility, decision notes on list rows, the approver queue and nav counts.

The routing matrix itself (global off, exempt, centre off, fallbacks) is in test_routing.py.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.masterdata.models import CostCentre, CostCentreApprover
from apps.notifications.models import EmailOutbox
from apps.platform_config.models import SiteConfig
from apps.shipments.models import ApprovalRound, ShipmentRequest

pytestmark = pytest.mark.django_db

GIULIA = "g.ferrari@diasorin.com"


# ------------------------------------------------------------------ helpers
def configure(**kw):
    cfg = SiteConfig.load()
    for k, v in kw.items():
        setattr(cfg, k, v)
    cfg.save()


def login(sign_in, email):
    """A signed-in client for `email` (a session, without the OTP rate limit of many real sign-ins)."""
    client = APIClient()
    client.force_login(User.objects.get(email=email))
    session = client.session  # what auth sessions.start_session stamps; the limits middleware needs it
    now = timezone.now().timestamp()
    session["login_at"] = session["last_activity"] = now
    session.save()
    return client


@pytest.fixture
def giulia_api(world, sign_in):
    return login(sign_in, GIULIA)


@pytest.fixture
def submitted(marco_api, complete_draft):
    """Submit a new request as Marco; returns its reference (status Pending approval with Giulia)."""

    def _submit(**over):
        d = complete_draft(**over)
        r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
        assert r.status_code == 200, r.content
        return d["reference"]

    return _submit


def get(api, ref):
    r = api.get(f"/api/requests/{ref}")
    assert r.status_code == 200, r.content
    return r.json()


def act(api, ref, action, body=None, expect=200):
    r = api.post(f"/api/requests/{ref}/{action}", body or {}, format="json")
    assert r.status_code == expect, (action, r.status_code, r.content)
    return r.json()


def revise(api, ref, **data):
    """Save draft while revising (the status must not change)."""
    version = get(api, ref)["version"]
    r = api.patch(f"/api/requests/{ref}/draft", {**data, "version": version}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def resubmit(api, ref):
    return act(api, ref, "submit", {"declaration": True})


def req_of(ref):
    return ShipmentRequest.objects.get(reference=ref)


def keys(ref, to=None):
    rows = EmailOutbox.objects.filter(request__reference=ref).exclude(template_key="otp")
    if to:
        rows = rows.filter(to_addresses=[to])
    return sorted(rows.values_list("template_key", flat=True))


# ------------------------------------------------------------------ routing: what the matrix test does not cover
def test_self_approval_with_a_co_approver_goes_to_the_co_approver_only(
    world, make_user, marco_api, complete_draft
):
    CostCentreApprover.objects.create(cost_centre=world["cc"], user=world["marco"])
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    rnd = req_of(d["reference"]).approval_rounds.get()
    assert [u.email for u in rnd.eligible_approvers.all()] == [GIULIA]


def test_held_round_cannot_be_approved_until_an_admin_reassigns(
    world, make_user, sign_in, marco_api, submitted, giulia_api
):
    CostCentreApprover.objects.all().delete()
    configure(no_approver_fallback="HOLD")
    ref = submitted()
    assert req_of(ref).approval_rounds.get().state == "HELD"
    admin = make_user("admin@diasorin.com", admin=True)
    admin_api = login(sign_in, admin.email)
    act(admin_api, ref, "approve", expect=409)  # held: not even an admin can decide
    out = act(admin_api, ref, "reassign-approver", {"email": GIULIA, "reason": "covering"})
    assert out["status"] == "PENDING_APPROVAL"
    rnd = req_of(ref).approval_rounds.get()
    assert rnd.state == "PENDING" and [u.email for u in rnd.eligible_approvers.all()] == [GIULIA]
    assert "approvalRequired" in keys(ref, GIULIA)
    assert act(giulia_api, ref, "approve")["status"] == "TO_VERIFY"


# ------------------------------------------------------------------ approve / reject
def test_approve_moves_to_verify_and_tells_the_requester_and_customer_management(
    world, marco_api, giulia_api, submitted
):
    ref = submitted()
    out = act(giulia_api, ref, "approve", {"comment": "Looks fine"})
    assert out["status"] == "TO_VERIFY"
    rnd = req_of(ref).approval_rounds.get()
    assert rnd.state == "APPROVED" and rnd.decided_by.email == GIULIA and rnd.decided_at
    ev = req_of(ref).events.get(action="Approved")
    assert (ev.from_status, ev.to_status, ev.actor_role, ev.in_conversation, ev.note) == (
        "PENDING_APPROVAL",
        "TO_VERIFY",
        "approver",
        True,
        "Looks fine",
    )
    assert "approved" in keys(ref, "m.rossi@diasorin.com")
    assert "oeNew" in keys(ref, SiteConfig.load().customer_mgmt_mailbox)


def test_approve_by_a_user_who_is_not_eligible_is_403_and_twice_is_409(
    world, make_user, sign_in, marco_api, giulia_api, submitted
):
    ref = submitted()
    act(marco_api, ref, "approve", expect=403)  # the requester is no approver
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    act(admin_api, ref, "approve", expect=403)  # admins decide only when escalated or reassigned
    assert req_of(ref).status == "PENDING_APPROVAL"
    act(giulia_api, ref, "approve")
    act(giulia_api, ref, "approve", expect=409)
    act(giulia_api, ref, "reject", {"comment": "late"}, expect=409)


def test_reject_needs_a_reason_only_when_the_setting_says_so(world, giulia_api, submitted):
    ref = submitted()
    act(giulia_api, ref, "reject", {}, expect=400)
    act(giulia_api, ref, "reject", {"comment": "  "}, expect=400)
    assert req_of(ref).status == "PENDING_APPROVAL"
    configure(reject_comment_required=False)
    assert act(giulia_api, ref, "reject", {})["status"] == "REJECTED"


def test_reject_resubmit_makes_round_two_and_round_one_stays_rejected(
    world, marco_api, giulia_api, submitted
):
    ref = submitted()
    act(giulia_api, ref, "reject", {"comment": "Wrong cost centre"})
    ev = req_of(ref).events.get(action="Rejected")
    assert (ev.from_status, ev.to_status, ev.note, ev.in_conversation) == (
        "PENDING_APPROVAL",
        "REJECTED",
        "Wrong cost centre",
        True,
    )
    assert "rejected" in keys(ref, "m.rossi@diasorin.com")
    out = resubmit(marco_api, ref)
    assert out["status"] == "PENDING_APPROVAL"
    r1, r2 = req_of(ref).approval_rounds.order_by("round_number")
    assert (r1.state, r2.state, r2.round_number) == ("REJECTED", "PENDING", 2)
    ev = req_of(ref).events.get(action="Resubmitted")
    assert (ev.from_status, ev.to_status, ev.in_conversation) == ("REJECTED", "PENDING_APPROVAL", True)
    assert ev.note.startswith("Corrected and resubmitted")
    # the approver who rejected it is told it was corrected, and approves round two
    assert "resubmitted" in keys(ref, GIULIA) and "approvalRequired" in keys(ref, GIULIA)
    assert act(giulia_api, ref, "approve")["status"] == "TO_VERIFY"


# ------------------------------------------------------------------ DSF-04.04: revise and resubmit
def test_ac_04_04_1_a_rejected_request_returns_to_the_approver(world, marco_api, giulia_api, submitted):
    ref = submitted()
    act(giulia_api, ref, "reject", {"comment": "Fix the lot"})
    assert "revise" in get(marco_api, ref)["available_actions"]
    assert resubmit(marco_api, ref)["status"] == "PENDING_APPROVAL"
    assert giulia_api.get("/api/approvals").json()["results"][0]["reference"] == ref


def _approved_then_returned(marco_api, giulia_api, cm_api, submitted):
    ref = submitted()
    act(giulia_api, ref, "approve")
    act(cm_api, ref, "return", {"note": "Phone number missing"})
    assert get(marco_api, ref)["status"] == "RETURNED"
    return ref


@pytest.fixture
def cm_api(world, make_user, sign_in):
    return login(sign_in, make_user("cm@diasorin.com", customer_management=True).email)


def test_ac_04_04_2_returned_after_approval_with_the_same_cost_centre_keeps_the_approval(
    world, marco_api, giulia_api, cm_api, submitted
):
    ref = _approved_then_returned(marco_api, giulia_api, cm_api, submitted)
    out = resubmit(marco_api, ref)
    assert out["status"] == "TO_VERIFY"
    assert req_of(ref).approval_rounds.count() == 1  # no new round
    ev = req_of(ref).events.get(action="Resubmitted")
    assert (ev.from_status, ev.to_status) == ("RETURNED", "TO_VERIFY")
    assert "approval retained" in ev.note
    assert "resubmitted" in keys(ref, "cm@diasorin.com")  # whoever sent it back is told


def test_ac_04_04_3_changing_the_cost_centre_on_a_returned_request_routes_it_again(
    world, marco_api, giulia_api, cm_api, submitted
):
    cc2 = CostCentre.objects.create(code="CC-4411", name="Lab", approval_required=True)
    CostCentreApprover.objects.create(cost_centre=cc2, user=world["giulia"])
    ref = _approved_then_returned(marco_api, giulia_api, cm_api, submitted)
    revise(marco_api, ref, cost_centre_code="CC-4411")
    out = resubmit(marco_api, ref)
    assert out["status"] == "PENDING_APPROVAL"
    assert req_of(ref).approval_rounds.count() == 2
    assert "approval retained" not in req_of(ref).events.get(action="Resubmitted").note


def test_ac_04_04_4_save_draft_while_revising_keeps_the_status_and_still_counts_as_a_resubmission(
    world, marco_api, giulia_api, cm_api, submitted
):
    # returned + approved + same cost centre: Revise -> Save as draft -> Submit == AC-04.04.2
    ref = _approved_then_returned(marco_api, giulia_api, cm_api, submitted)
    assert revise(marco_api, ref, consignee_city="Torino")["status"] == "RETURNED"  # never back to Draft
    out = resubmit(marco_api, ref)
    assert out["status"] == "TO_VERIFY" and req_of(ref).approval_rounds.count() == 1
    assert req_of(ref).events.filter(action="Resubmitted").count() == 1
    assert [e.action for e in req_of(ref).events.filter(action__in=["Submitted", "Resubmitted"])] == [
        "Submitted",
        "Resubmitted",
    ]

    # rejected: Revise -> Save as draft -> Submit goes to the approver again, logged as Resubmitted
    ref2 = submitted()
    act(giulia_api, ref2, "reject", {"comment": "No"})
    assert revise(marco_api, ref2, consignee_city="Milano")["status"] == "REJECTED"
    assert resubmit(marco_api, ref2)["status"] == "PENDING_APPROVAL"
    assert req_of(ref2).events.filter(action="Resubmitted").count() == 1
    assert req_of(ref2).approval_rounds.count() == 2


# ------------------------------------------------------------------ return
def test_only_customer_management_can_return_and_a_note_is_required(
    world, marco_api, giulia_api, cm_api, submitted
):
    ref = submitted()
    act(cm_api, ref, "return", {"note": "x"}, expect=409)  # still waiting for approval
    act(giulia_api, ref, "approve")
    act(giulia_api, ref, "return", {"note": "x"}, expect=403)
    act(marco_api, ref, "return", {"note": "x"}, expect=403)
    act(cm_api, ref, "return", {}, expect=400)
    out = act(cm_api, ref, "return", {"note": "Phone number missing"})
    assert out["status"] == "RETURNED"
    r = req_of(ref)
    assert r.cm_owner.email == "cm@diasorin.com"  # the first customer-management action claims it
    ev = r.events.get(action="Returned")
    assert (ev.from_status, ev.to_status, ev.actor_role, ev.note) == (
        "TO_VERIFY",
        "RETURNED",
        "customer_management",
        "Phone number missing",
    )
    assert "returned" in keys(ref, "m.rossi@diasorin.com")


# ------------------------------------------------------------------ cancel
@pytest.mark.parametrize(
    "status,owner_ok",
    [
        ("PENDING_APPROVAL", True),
        ("TO_VERIFY", True),
        ("REJECTED", True),
        ("RETURNED", True),
        ("VERIFIED", False),
        ("PACKED", False),
        ("IN_TRANSIT", False),
        ("DELIVERED", False),
        ("CANCELLED", False),
    ],
)
def test_cancel_by_the_owner_depends_on_the_status(world, marco_api, submitted, status, owner_ok):
    ref = submitted()
    ShipmentRequest.objects.filter(reference=ref).update(status=status)
    act(marco_api, ref, "cancel", {"reason": "changed my mind"}, expect=200 if owner_ok else 409)
    assert req_of(ref).status == ("CANCELLED" if owner_ok else status)


@pytest.mark.parametrize("status", ["PENDING_APPROVAL", "TO_VERIFY", "VERIFIED", "PACKED", "IN_TRANSIT"])
def test_admin_can_cancel_any_open_request_but_not_a_closed_one(world, make_user, sign_in, submitted, status):
    ref = submitted()
    ShipmentRequest.objects.filter(reference=ref).update(status=status)
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    assert act(admin_api, ref, "cancel", {"reason": "duplicate"})["status"] == "CANCELLED"
    act(admin_api, ref, "cancel", expect=409)  # already closed


def test_cancel_by_a_stranger_or_an_approver_is_refused_and_a_draft_can_be_cancelled(
    world, marco_api, giulia_api, submitted, new_draft
):
    ref = submitted()
    act(giulia_api, ref, "cancel", expect=403)  # approvers decide, they do not cancel
    assert req_of(ref).status == "PENDING_APPROVAL"
    draft = new_draft()
    assert act(marco_api, draft["reference"], "cancel")["status"] == "CANCELLED"


def test_cancel_closes_the_open_round_and_tells_the_people_working_on_it(
    world, make_user, sign_in, marco_api, giulia_api, submitted
):
    ref = submitted()
    act(marco_api, ref, "cancel", {"reason": "not needed"})
    assert req_of(ref).approval_rounds.get().state == "SUPERSEDED"
    assert "cancelled" in keys(ref, GIULIA)
    assert giulia_api.get("/api/me/counts").json()["approvals_pending"] == 0  # out of the queue
    ev = req_of(ref).events.get(action="Cancelled")
    assert (ev.from_status, ev.to_status, ev.actor_role, ev.note) == (
        "PENDING_APPROVAL",
        "CANCELLED",
        "requester",
        "not needed",
    )
    # an admin cancelling someone else's request in verification tells the requester and customer management
    ref2 = submitted()
    act(giulia_api, ref2, "approve")
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    act(admin_api, ref2, "cancel", {"reason": "stock issue"})
    assert "cancelled" in keys(ref2, "m.rossi@diasorin.com")
    assert "cancelled" in keys(ref2, SiteConfig.load().customer_mgmt_mailbox)


# ------------------------------------------------------------------ admin reassign / skip
def test_admin_reassign_changes_the_eligible_approver_and_logs_it(
    world, make_user, sign_in, marco_api, giulia_api, submitted
):
    other = make_user("other@diasorin.com", first_name="Olga")
    ref = submitted()
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    act(giulia_api, ref, "reassign-approver", {"email": other.email}, expect=403)
    act(admin_api, ref, "reassign-approver", {"email": "nobody@diasorin.com"}, expect=400)
    act(admin_api, ref, "reassign-approver", {"email": "m.rossi@diasorin.com"}, expect=400)  # self-approval
    act(admin_api, ref, "reassign-approver", {"email": other.email, "reason": "Giulia is away"})
    rnd = req_of(ref).approval_rounds.get()
    assert [u.email for u in rnd.eligible_approvers.all()] == [other.email]
    ev = req_of(ref).events.get(action="Approver reassigned")
    assert (ev.from_status, ev.to_status, ev.actor_role) == ("PENDING_APPROVAL", "PENDING_APPROVAL", "admin")
    assert "Giulia is away" in ev.note
    act(giulia_api, ref, "approve", expect=403)  # no longer hers
    other_api = login(sign_in, other.email)
    assert act(other_api, ref, "approve")["status"] == "TO_VERIFY"


def test_admin_skip_approval_goes_to_verify_and_logs_it(world, make_user, sign_in, giulia_api, submitted):
    ref = submitted()
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    act(giulia_api, ref, "skip-approval", expect=403)
    assert act(admin_api, ref, "skip-approval", {"reason": "urgent"})["status"] == "TO_VERIFY"
    rnd = req_of(ref).approval_rounds.get()
    assert (rnd.state, rnd.skip_reason, rnd.required) == ("NOT_REQUIRED", "ADMIN_SKIP", True)
    ev = req_of(ref).events.get(action="Approval skipped")
    assert (ev.from_status, ev.to_status, ev.actor_role, ev.note) == (
        "PENDING_APPROVAL",
        "TO_VERIFY",
        "admin",
        "urgent",
    )
    assert "oeNew" in keys(ref, SiteConfig.load().customer_mgmt_mailbox)
    act(admin_api, ref, "skip-approval", expect=409)


def test_every_transition_writes_exactly_one_event_with_the_right_from_to_and_role(
    world, make_user, sign_in, marco_api, giulia_api, cm_api, submitted
):
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    other = make_user("other@diasorin.com")
    cases = [  # (client, action, body, expected from, to, role)
        (giulia_api, "approve", {}, "PENDING_APPROVAL", "TO_VERIFY", "approver"),
        (giulia_api, "reject", {"comment": "no"}, "PENDING_APPROVAL", "REJECTED", "approver"),
        (marco_api, "cancel", {}, "PENDING_APPROVAL", "CANCELLED", "requester"),
        (admin_api, "skip-approval", {}, "PENDING_APPROVAL", "TO_VERIFY", "admin"),
        (
            admin_api,
            "reassign-approver",
            {"email": other.email},
            "PENDING_APPROVAL",
            "PENDING_APPROVAL",
            "admin",
        ),
    ]
    for client, action, body, frm, to, role in cases:
        ref = submitted()
        before = req_of(ref).events.count()
        act(client, ref, action, body)
        new = list(req_of(ref).events.order_by("id"))[before:]
        assert len(new) == 1, (action, [e.action for e in new])
        assert (new[0].from_status, new[0].to_status, new[0].actor_role) == (frm, to, role), action
    ref = submitted()
    act(giulia_api, ref, "approve")
    before = req_of(ref).events.count()
    act(cm_api, ref, "return", {"note": "n"})
    new = list(req_of(ref).events.order_by("id"))[before:]
    assert [(e.from_status, e.to_status, e.actor_role) for e in new] == [
        ("TO_VERIFY", "RETURNED", "customer_management")
    ]
    before = req_of(ref).events.count()
    resubmit(marco_api, ref)
    assert req_of(ref).events.count() == before + 1


# ------------------------------------------------------------------ visibility
def test_who_can_see_which_request(world, make_user, sign_in, marco_api, new_draft, submitted, cm_api):
    ref = submitted()
    draft = new_draft()["reference"]
    stranger = login(sign_in, make_user("x@diasorin.com").email)
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    giulia = login(sign_in, GIULIA)
    elsewhere_cc = CostCentre.objects.create(code="CC-9999", name="Elsewhere", approval_required=True)
    elsewhere = make_user("e@diasorin.com")
    CostCentreApprover.objects.create(cost_centre=elsewhere_cc, user=elsewhere)
    elsewhere_api = login(sign_in, elsewhere.email)

    def status(client, r):
        return client.get(f"/api/requests/{r}").status_code

    assert status(marco_api, ref) == 200 and status(marco_api, draft) == 200  # the owner sees everything
    assert status(giulia, ref) == 200  # approver of the cost centre and eligible on the round
    assert status(cm_api, ref) == 200  # customer management: everything that is not a draft
    assert status(admin_api, ref) == 200
    for client in (giulia, cm_api, admin_api, stranger):
        assert status(client, draft) == 404  # drafts are private to their owner
    assert status(stranger, ref) == 404 and status(elsewhere_api, ref) == 404


def test_an_approver_eligible_on_a_round_sees_it_even_outside_their_cost_centres(
    world, make_user, sign_in, submitted
):
    ref = submitted()
    other = make_user("other@diasorin.com")
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    other_api = login(sign_in, other.email)
    assert other_api.get(f"/api/requests/{ref}").status_code == 404
    act(admin_api, ref, "reassign-approver", {"email": other.email})
    assert other_api.get(f"/api/requests/{ref}").status_code == 200
    assert [r["reference"] for r in other_api.get("/api/approvals").json()["results"]] == [ref]


def test_events_are_filtered_by_role_the_requester_never_sees_internal_notes(
    world, marco_api, giulia_api, cm_api, submitted
):
    ref = submitted()
    act(giulia_api, ref, "comments", {"kind": "note", "text": "Internal: check budget"}, expect=201)
    act(cm_api, ref, "comments", {"kind": "question", "text": "Is the phone right?"}, expect=201)
    act(marco_api, ref, "comments", {"kind": "comment", "text": "Yes it is"}, expect=201)

    def kinds(api, path):
        data = api.get(path).json()
        return [e["kind"] for e in (data["events"] if isinstance(data, dict) else data)]

    for path in (f"/api/requests/{ref}", f"/api/requests/{ref}/events", f"/api/requests/{ref}/comments"):
        assert "NOTE" not in kinds(marco_api, path), path
        assert "NOTE" in kinds(giulia_api, path), path
    assert "QUESTION" in kinds(marco_api, f"/api/requests/{ref}/comments")
    # conversation = in_conversation rows; events = the audit trail, which also holds the submit
    assert len(marco_api.get(f"/api/requests/{ref}/events").json()) > len(
        marco_api.get(f"/api/requests/{ref}/comments").json()
    )


def test_posting_rules_and_the_question_email(world, marco_api, giulia_api, submitted, new_draft):
    ref = submitted()
    act(
        marco_api, ref, "comments", {"kind": "question", "text": "hi"}, expect=403
    )  # the requester cannot ask
    act(marco_api, ref, "comments", {"kind": "note", "text": "hi"}, expect=403)
    act(giulia_api, ref, "comments", {"kind": "comment", "text": ""}, expect=400)
    act(giulia_api, ref, "comments", {"kind": "comment", "text": "x" * 2001}, expect=400)
    act(giulia_api, ref, "comments", {"kind": "question", "text": "Which lot?"}, expect=201)
    assert "question" in keys(ref, "m.rossi@diasorin.com")
    ev = req_of(ref).events.get(kind="QUESTION")
    assert (ev.from_status, ev.to_status, ev.actor_role, ev.in_conversation) == ("", "", "approver", True)
    act(marco_api, new_draft()["reference"], "comments", {"kind": "comment", "text": "x"}, expect=409)


# ------------------------------------------------------------------ list rows, queue, counts
def test_list_rows_carry_the_latest_decision_note(world, marco_api, giulia_api, cm_api, submitted):
    ref = submitted()
    row = lambda: next(  # noqa: E731
        r for r in marco_api.get("/api/requests").json()["results"] if r["reference"] == ref
    )
    assert row()["decision_note"] is None
    act(giulia_api, ref, "reject", {"comment": "Wrong cost centre"})
    assert (row()["decision_note"], row()["decision_by"]) == ("Wrong cost centre", "Giulia Ferrari")
    resubmit(marco_api, ref)
    assert row()["decision_note"] is None  # no longer rejected
    act(giulia_api, ref, "approve")
    act(cm_api, ref, "return", {"note": "Phone number missing"})
    assert (row()["decision_note"], row()["decision_by"]) == ("Phone number missing", "Test")


def test_list_rows_do_not_add_a_query_per_request(
    world, marco_api, giulia_api, submitted, django_assert_max_num_queries
):
    refs = [submitted() for _ in range(3)]
    for ref in refs:
        act(giulia_api, ref, "reject", {"comment": "no"})
    with django_assert_max_num_queries(25):
        assert marco_api.get("/api/requests").status_code == 200


def test_approver_queue_has_age_sla_class_stats_and_filters(world, marco_api, giulia_api, submitted):
    configure(sla_hours=24, escalate_hours=48)
    fresh, aging, old = submitted(), submitted(), submitted()
    now = timezone.now()
    ApprovalRound.objects.filter(request__reference=aging).update(started_at=now - timedelta(hours=30))
    ApprovalRound.objects.filter(request__reference=old).update(started_at=now - timedelta(hours=60))
    body = giulia_api.get("/api/approvals").json()
    rows = {r["reference"]: r for r in body["results"]}
    assert (rows[fresh]["sla_class"], rows[aging]["sla_class"], rows[old]["sla_class"]) == (
        "ok",
        "warn",
        "over",
    )
    assert rows[aging]["age_hours"] == 30 and rows[old]["escalated"] and not rows[fresh]["escalated"]
    assert rows[fresh]["can_decide"] and rows[fresh]["cost_centre_code"] == "CC-4410"
    assert body["stats"] == {"awaiting": 3, "over_sla": 2, "decided": 0, "approved_this_month": 0}

    act(giulia_api, fresh, "approve", {"comment": "ok"})
    pending = giulia_api.get("/api/approvals?filter=pending").json()
    assert len(pending["results"]) == 2 and pending["stats"]["awaiting"] == 2
    decided = giulia_api.get("/api/approvals?filter=decided").json()
    assert [r["reference"] for r in decided["results"]] == [fresh]
    assert decided["results"][0]["decision_note"] == "ok" and decided["results"][0]["can_decide"] is False
    assert decided["stats"]["decided"] == 1 and decided["stats"]["approved_this_month"] == 1
    assert len(giulia_api.get("/api/approvals?filter=all").json()["results"]) == 3
    assert [r["reference"] for r in giulia_api.get(f"/api/approvals?q={old}").json()["results"]] == [old]
    assert giulia_api.get("/api/approvals?filter=nope").status_code == 400
    assert marco_api.get("/api/approvals").status_code == 403  # the requester has no approver view


def test_my_cost_centres_and_nav_counts(world, make_user, sign_in, marco_api, giulia_api, submitted):
    second = make_user("second@diasorin.com", first_name="Second", last_name="Approver")
    CostCentreApprover.objects.create(cost_centre=world["cc"], user=second)
    submitted()
    submitted()
    rows = giulia_api.get("/api/approvals/my-cost-centres").json()
    assert rows == [
        {
            "code": "CC-4410",
            "name": "Warehouse",
            "approval_required": True,
            "co_approvers": ["Second Approver"],
            "pending": 2,
        }
    ]
    assert giulia_api.get("/api/me/counts").json() == {"approvals_pending": 2, "my_open_requests": 0}
    assert marco_api.get("/api/me/counts").json() == {"approvals_pending": 0, "my_open_requests": 2}


# ------------------------------------------------------------------ available_actions
def test_available_actions_match_what_the_services_allow(
    world, make_user, sign_in, marco_api, giulia_api, cm_api, submitted, new_draft
):
    admin_api = login(sign_in, make_user("admin@diasorin.com", admin=True).email)
    ref = submitted()
    expected = {  # who may do what on a request waiting for approval
        "marco": (marco_api, {"cancel", "comment", "duplicate"}),
        "giulia": (giulia_api, {"approve", "reject", "comment", "question", "note"}),
        "cm": (cm_api, {"comment", "question", "note"}),
        "admin": (admin_api, {"cancel", "reassign_approver", "skip_approval", "comment", "question", "note"}),
    }
    for who, (client, actions) in expected.items():
        assert set(get(client, ref)["available_actions"]) == actions, who
    # every listed action works, and an unlisted one is refused
    act(marco_api, ref, "cancel")
    assert get(marco_api, ref)["available_actions"] == ["comment", "duplicate"]
    act(giulia_api, ref, "approve", expect=409)

    ref2 = submitted()
    assert "approve" in get(giulia_api, ref2)["available_actions"]
    act(giulia_api, ref2, "approve")
    assert "approve" not in get(giulia_api, ref2)["available_actions"]
    assert "return" in get(cm_api, ref2)["available_actions"]
    act(cm_api, ref2, "return", {"note": "n"})
    assert set(get(marco_api, ref2)["available_actions"]) == {"revise", "cancel", "comment", "duplicate"}
    draft = new_draft()["reference"]
    assert set(get(marco_api, draft)["available_actions"]) == {"edit", "cancel"}
