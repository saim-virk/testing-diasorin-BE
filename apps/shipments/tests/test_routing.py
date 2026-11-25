"""Routing matrix (REQUIREMENTS section 5) and the guarantee that the cost-centre hint equals what submit does."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.enums import AppRole
from apps.accounts.services.roles import assign_role
from apps.masterdata.models import CostCentreApprover
from apps.notifications.models import EmailOutbox
from apps.platform_config.models import SiteConfig
from apps.shipments.models import ShipmentRequest

pytestmark = pytest.mark.django_db


def configure(**kw):
    cfg = SiteConfig.load()
    for k, v in kw.items():
        setattr(cfg, k, v)
    cfg.save()


def scenario_global_off(w, mk):
    configure(approval_global_enabled=False)


def scenario_exempt(w, mk):
    w["marco"].approval_exempt = True
    w["marco"].save()


def scenario_centre_off(w, mk):
    w["cc"].approval_required = False
    w["cc"].save()


def scenario_approvers(w, mk):
    pass


def scenario_self_only_admin(w, mk):  # the only approver is the requester; self-approval blocked
    CostCentreApprover.objects.all().delete()
    CostCentreApprover.objects.create(cost_centre=w["cc"], user=w["marco"])
    mk("admin@diasorin.com", admin=True)


def scenario_self_allowed(w, mk):
    CostCentreApprover.objects.all().delete()
    CostCentreApprover.objects.create(cost_centre=w["cc"], user=w["marco"])
    configure(self_approval_mode="AUTO_APPROVE")


def scenario_self_only_and_sole_admin(w, mk):  # requester is the only approver and the only admin
    CostCentreApprover.objects.all().delete()
    CostCentreApprover.objects.create(cost_centre=w["cc"], user=w["marco"])
    assign_role(w["marco"], AppRole.ADMIN)


def scenario_none_requester_is_sole_admin(w, mk):  # no approver, ADMIN fallback, only admin is the requester
    CostCentreApprover.objects.all().delete()
    assign_role(w["marco"], AppRole.ADMIN)


def scenario_none_requester_admin_and_other_admin(w, mk):  # the requester is never among the eligible admins
    CostCentreApprover.objects.all().delete()
    assign_role(w["marco"], AppRole.ADMIN)
    mk("admin@diasorin.com", admin=True)


def scenario_none_admin(w, mk):
    CostCentreApprover.objects.all().delete()
    mk("admin@diasorin.com", admin=True)


def scenario_none_skip(w, mk):
    CostCentreApprover.objects.all().delete()
    configure(no_approver_fallback="SKIP")


def scenario_none_hold(w, mk):
    CostCentreApprover.objects.all().delete()
    configure(no_approver_fallback="HOLD")


def scenario_none_admin_but_no_admin_exists(w, mk):
    CostCentreApprover.objects.all().delete()


# name, setup, (required, why, status, round state, skip reason, approver emails, escalated)
MATRIX = [
    (
        "global_off",
        scenario_global_off,
        (False, "global_off", "TO_VERIFY", "NOT_REQUIRED", "GLOBAL_OFF", [], False),
    ),
    (
        "exempt",
        scenario_exempt,
        (False, "exempt", "TO_VERIFY", "NOT_REQUIRED", "REQUESTER_EXEMPT", [], False),
    ),
    (
        "centre_off",
        scenario_centre_off,
        (False, "cost_centre_off", "TO_VERIFY", "NOT_REQUIRED", "CENTRE_OFF", [], False),
    ),
    (
        "approvers",
        scenario_approvers,
        (True, "required", "PENDING_APPROVAL", "PENDING", None, ["g.ferrari@diasorin.com"], False),
    ),
    (
        "self_removed_then_admin",
        scenario_self_only_admin,
        (True, "no_approver_admin", "PENDING_APPROVAL", "PENDING", None, ["admin@diasorin.com"], True),
    ),
    (
        "self_allowed",
        scenario_self_allowed,
        (True, "self_auto_approved", "TO_VERIFY", "APPROVED", "SELF_AUTO_APPROVED", [], False),
    ),
    (
        "self_only_sole_admin",
        scenario_self_only_and_sole_admin,
        (True, "self_auto_approved", "TO_VERIFY", "APPROVED", "SELF_AUTO_APPROVED", [], False),
    ),
    (
        "none_requester_sole_admin",
        scenario_none_requester_is_sole_admin,
        (True, "self_auto_approved", "TO_VERIFY", "APPROVED", "SELF_AUTO_APPROVED", [], False),
    ),
    (
        "none_requester_admin_other_admin",
        scenario_none_requester_admin_and_other_admin,
        (True, "no_approver_admin", "PENDING_APPROVAL", "PENDING", None, ["admin@diasorin.com"], True),
    ),
    (
        "none_admin",
        scenario_none_admin,
        (True, "no_approver_admin", "PENDING_APPROVAL", "PENDING", None, ["admin@diasorin.com"], True),
    ),
    (
        "none_skip",
        scenario_none_skip,
        (False, "no_approver_skip", "TO_VERIFY", "NOT_REQUIRED", "NO_APPROVER_SKIP", [], False),
    ),
    (
        "none_hold",
        scenario_none_hold,
        (True, "no_approver_hold", "PENDING_APPROVAL", "HELD", None, [], False),
    ),
    (
        "none_admin_no_admin",
        scenario_none_admin_but_no_admin_exists,
        (True, "self_auto_approved", "TO_VERIFY", "APPROVED", "SELF_AUTO_APPROVED", [], False),
    ),
]


@pytest.mark.parametrize("name,setup,expected", MATRIX, ids=[m[0] for m in MATRIX])
def test_routing_matrix_and_hint_matches_submit(
    name, setup, expected, world, make_user, marco_api, complete_draft
):
    required, why, status, state, skip, approver_emails, escalated = expected
    setup(world, make_user)

    # the hint (dry run) ...
    hint = marco_api.get("/api/me").json()["approval_hint"]
    assert (hint["required"], hint["why"]) == (required, why)
    listed = next(c for c in marco_api.get("/api/masterdata/cost-centres").json() if c["code"] == "CC-4410")
    assert listed["approval_hint"] == hint

    # ... equals what submit really does
    d = complete_draft()
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["status"] == status
    req = ShipmentRequest.objects.get(reference=d["reference"])
    rnd = req.approval_rounds.get()
    assert (rnd.required, rnd.state, rnd.skip_reason, rnd.escalated_to_admins) == (
        required,
        state,
        skip,
        escalated,
    )
    assert sorted(u.email for u in rnd.eligible_approvers.all()) == approver_emails
    names = [
        u.get_full_name() or u.email
        for u in rnd.eligible_approvers.order_by("last_name", "first_name", "email")
    ]
    assert hint["approvers"] == names

    # emails: confirmation to the requester; approvalRequired to approvers or oeNew to customer management
    sent = {(m.template_key, tuple(m.to_addresses)) for m in EmailOutbox.objects.exclude(template_key="otp")}
    assert ("submitted", ("m.rossi@diasorin.com",)) in sent
    if required and state != "APPROVED":
        assert {("approvalRequired", (e,)) for e in approver_emails} <= sent
        assert not any(k == "oeNew" for k, _ in sent)
    else:
        assert ("oeNew", (SiteConfig.load().customer_mgmt_mailbox,)) in sent
        assert not any(k == "approvalRequired" for k, _ in sent)


def _submit_as_marco(marco_api, complete_draft):
    d = complete_draft()
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert r.status_code == 200, r.content
    return d["reference"], r.json()


def test_auto_approval_is_recorded_labelled_and_flagged_to_customer_management(
    world, marco_api, complete_draft
):
    scenario_self_allowed(world, None)
    ref, body = _submit_as_marco(marco_api, complete_draft)
    req = ShipmentRequest.objects.get(reference=ref)
    rnd = req.approval_rounds.get()
    assert (rnd.required, rnd.state, rnd.decided_by, rnd.skip_reason) == (
        True, "APPROVED", None, "SELF_AUTO_APPROVED"
    )  # fmt: skip
    ev = req.events.get(action="Approved automatically")
    assert ev.in_conversation and ev.actor is None and "requester is an approver" in ev.note
    row = marco_api.get("/api/requests").json()["results"][0]
    assert row["approval"] == {"state": "AUTO_APPROVED", "names": []}
    en = marco_api.get("/api/requests/export.csv").content.decode("utf-8-sig")
    assert "Approved automatically (self)" in en
    mail = EmailOutbox.objects.get(template_key="oeNew")
    assert "self-approved" in mail.subject or "self-approved" in mail.body
    assert not EmailOutbox.objects.filter(template_key="approvalRequired").exists()
    assert body["next_steps"]["approval_required"] is False


def test_auto_approval_labels_in_italian(world, marco_api, complete_draft):
    scenario_self_allowed(world, None)
    _submit_as_marco(marco_api, complete_draft)
    it = marco_api.get("/api/requests/export.csv", headers={"Accept-Language": "it"}).content.decode(
        "utf-8-sig"
    )
    assert "Approvata automaticamente (autoapprovazione)" in it


def test_requester_cannot_approve_own_request_in_any_mode(world, marco_api, complete_draft):
    # even if eligibility were somehow set to the requester, the guard refuses (403)
    ref, _ = _submit_as_marco(marco_api, complete_draft)
    req = ShipmentRequest.objects.get(reference=ref)
    req.approval_rounds.get().eligible_approvers.add(world["marco"])
    assert marco_api.post(f"/api/requests/{ref}/approve", {}, format="json").status_code == 403
    assert "approve" not in marco_api.get(f"/api/requests/{ref}").json()["available_actions"]


def test_reassign_to_the_requester_is_refused(world, make_user, sign_in, marco_api, complete_draft):
    make_user("admin@diasorin.com", admin=True)
    admin_api = sign_in("admin@diasorin.com", APIClient())
    CostCentreApprover.objects.all().delete()
    configure(no_approver_fallback="HOLD")
    ref, _ = _submit_as_marco(marco_api, complete_draft)
    r = admin_api.post(
        f"/api/requests/{ref}/reassign-approver", {"email": "m.rossi@diasorin.com"}, format="json"
    )
    assert r.status_code == 400


def test_held_round_notifies_nobody_but_the_requester(world, marco_api, complete_draft):
    CostCentreApprover.objects.all().delete()
    configure(no_approver_fallback="HOLD")
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    keys = [m.template_key for m in EmailOutbox.objects.exclude(template_key="otp")]
    assert keys == ["submitted"]


def test_submitted_email_carries_the_reference_and_uses_the_profile_language(
    world, marco_api, complete_draft
):
    world["marco"].language = "it"
    world["marco"].save()
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    mail = EmailOutbox.objects.get(template_key="submitted")
    assert d["reference"] in mail.subject and d["reference"] in mail.body
    assert "inviata" in mail.subject  # Italian template
    approval = EmailOutbox.objects.get(template_key="approvalRequired")
    assert (
        d["reference"] in approval.subject and "Azione richiesta" not in approval.subject
    )  # Giulia is English


def test_confirmation_data_for_an_approval_request_and_for_one_that_skips(world, marco_api, complete_draft):
    d = complete_draft()
    body = marco_api.post(
        f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json"
    ).json()
    ns = body["next_steps"]
    assert (
        body["status"] == "PENDING_APPROVAL"
        and ns["approval_required"]
        and ns["approvers"] == ["Giulia Ferrari"]
    )
    assert ns["reminder_hours"] == 24 and ns["escalate_hours"] == 48 and ns["specialised_courier"] is False
    configure(approval_global_enabled=False)
    d2 = complete_draft()
    body2 = marco_api.post(
        f"/api/requests/{d2['reference']}/submit", {"declaration": True}, format="json"
    ).json()
    assert body2["status"] == "TO_VERIFY" and body2["next_steps"]["approval_required"] is False
    assert body2["next_steps"]["approval_note"] == "GLOBAL_OFF"


def test_resubmit_after_rejection_starts_a_new_round(world, marco_api, complete_draft):
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    req = ShipmentRequest.objects.get(reference=d["reference"])
    rnd = req.approval_rounds.get()
    rnd.state = "REJECTED"
    rnd.save()
    req.status = "REJECTED"
    req.save()
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "PENDING_APPROVAL"
    assert req.approval_rounds.count() == 2 and req.events.filter(action="Resubmitted").exists()


def test_returned_goes_straight_to_verify_when_the_previous_round_was_not_required(
    world, marco_api, complete_draft
):
    configure(approval_global_enabled=False)
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    ShipmentRequest.objects.filter(reference=d["reference"]).update(status="RETURNED")
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert r.json()["status"] == "TO_VERIFY"


# ------------------------------------------------------------------ submit validation
def test_submit_revalidates_every_step_and_returns_the_first_failing_one(world, marco_api, complete_draft):
    d = complete_draft()
    from apps.masterdata.models import Branch

    Branch.objects.filter(code="DS-IT-SAL").update(
        is_active=False
    )  # master data changed after step 2 was saved
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    body = r.json()
    assert r.status_code == 400 and body["step"] == 2 and "recipient_code" in body["errors"]
    assert body["failed_steps"] == [2] and body["message"]
    assert ShipmentRequest.objects.get(reference=d["reference"]).status == "DRAFT"


def test_submit_needs_the_declaration(world, marco_api, complete_draft):
    d = complete_draft()
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": False}, format="json")
    assert r.status_code == 400 and r.json()["step"] == 5 and "declaration" in r.json()["errors"]
    ok = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert ok.status_code == 200 and ok.json()["declaration_accepted_at"]


def test_usa_request_end_to_end_like_the_done_when(world, marco_api, new_draft, payloads):
    d = new_draft()
    ref = d["reference"]
    us_answers = {
        k: "NO"
        for k in (
            "us_usda_guideline",
            "us_usda_permit",
            "us_attach_000614",
            "us_cdc_permit",
            "us_importer_certification_statement",
        )
    }
    body = {
        **payloads.step1(destination="USA"),
        **payloads.step2(
            recipient_code="DS-US-STW",
            reason_code=payloads.reason_eu,
            consignee_country_code="US",
            po_number="PO-9",
        ),
        **payloads.step3(
            lines=[payloads.line(pvari_code="P9996", temperature="DRY_ICE")], dangerous_features="INFECTIOUS"
        ),
        **payloads.step4(**us_answers),
    }
    saved = marco_api.patch(
        f"/api/requests/{ref}/draft", {**body, "version": d["version"]}, format="json"
    ).json()
    assert (
        saved["derived"]["hazard"] == "INFECTIOUS"
        and saved["overall_temperature"] == "DRY_ICE"
        and saved["po_required"] is True
    )
    reopened = marco_api.get(f"/api/requests/{ref}").json()
    assert reopened["lines"][0]["pvari_code"] == "P9996"
    r = marco_api.post(f"/api/requests/{ref}/submit", {"declaration": True}, format="json")
    assert r.status_code == 200 and r.json()["next_steps"]["specialised_courier"] is True
    listed = marco_api.get("/api/requests").json()["results"]
    assert listed[0]["reference"] == ref and listed[0]["status"] in ("PENDING_APPROVAL", "TO_VERIFY")
