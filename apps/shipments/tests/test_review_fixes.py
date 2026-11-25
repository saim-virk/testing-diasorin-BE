"""Session A review fixes (day 3): language of email sentences, HELD notice, duplicate ownership, Italian DRF
messages, CSV labels, attachment handling, 404 for unseen references."""

import csv
import io
import logging
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.notifications.models import EmailOutbox
from apps.platform_config.models import SiteConfig
from apps.shipments.models import ApprovalRound, Attachment, ShipmentRequest

from .test_routing import (
    scenario_global_off,
    scenario_none_admin,
    scenario_none_hold,
    scenario_none_skip,
)

pytestmark = pytest.mark.django_db


def submit(client, ref):
    return client.post(f"/api/requests/{ref}/submit", {"declaration": True}, format="json")


def mail(key):
    return EmailOutbox.objects.get(template_key=key)


def upload_pdf(client, ref, name="a.pdf"):
    f = SimpleUploadedFile(name, b"%PDF-1.4 x")
    return client.post(f"/api/requests/{ref}/attachments", {"kind": "MSDS", "file": f}, format="multipart")


# ------------------------------------------------------------------ 1 + 2: sentences per language and case
def test_italian_requester_gets_an_all_italian_submitted_email(world, marco_api, complete_draft):
    world["marco"].language = "it"
    world["marco"].save()
    submit(marco_api, complete_draft()["reference"])
    m = mail("submitted")
    text = m.subject + m.body
    assert "L'approvatore del tuo centro di costo è stato avvisato." in text
    assert "Your" not in text and "approver has been" not in text


@pytest.mark.parametrize(
    "setup,sentence",
    [
        (lambda w, mk: None, "Your cost centre approver has been notified."),
        (
            scenario_none_admin,
            "There is no approver for this cost centre, so an administrator has been asked to approve.",
        ),
        (
            scenario_none_hold,
            "There is no approver for this cost centre. The request is on hold until an administrator assigns one.",
        ),
        (scenario_global_off, "Customer management will verify the data."),
    ],
    ids=["approvers", "escalated", "held", "no_approval"],
)
def test_next_step_sentence_per_routing_case(world, make_user, marco_api, complete_draft, setup, sentence):
    setup(world, make_user)
    submit(marco_api, complete_draft()["reference"])
    m = mail("submitted")
    assert sentence in m.subject + m.body


def test_oenew_summary_is_in_the_recipients_language(world, make_user, marco_api, complete_draft):
    scenario_global_off(world, make_user)
    make_user("customer.mgmt@diasorin.com", language="it")
    cfg = SiteConfig.load()
    cfg.customer_mgmt_mailbox = "customer.mgmt@diasorin.com"
    cfg.save()
    submit(marco_api, complete_draft()["reference"])
    assert "approvazione non necessaria" in mail("oeNew").subject


@pytest.mark.parametrize(
    "round_state,expected",
    [("APPROVED", "approval already given"), ("NOT_REQUIRED", "no approval needed")],
)
def test_resubmit_without_reapproval_summary_follows_the_last_round(
    world, make_user, marco_api, complete_draft, round_state, expected
):
    if round_state == "NOT_REQUIRED":
        scenario_global_off(world, make_user)
    ref = complete_draft()["reference"]
    submit(marco_api, ref)
    ApprovalRound.objects.filter(request__reference=ref).update(state=round_state)
    ShipmentRequest.objects.filter(reference=ref).update(status="RETURNED")
    EmailOutbox.objects.all().delete()
    assert submit(marco_api, ref).status_code == 200
    assert expected in mail("oeNew").subject


# ------------------------------------------------------------------ 3: HELD tells the administrators
def test_held_round_emails_every_active_administrator(world, make_user, marco_api, complete_draft):
    scenario_none_hold(world, make_user)
    make_user("admin1@diasorin.com", admin=True)
    make_user("admin2@diasorin.com", admin=True)
    make_user("gone@diasorin.com", admin=True, is_active=False)
    ref = complete_draft()["reference"]
    submit(marco_api, ref)
    rows = EmailOutbox.objects.filter(template_key="approvalHeld")
    assert sorted(r.to_addresses[0] for r in rows) == ["admin1@diasorin.com", "admin2@diasorin.com"]
    assert ref in rows[0].subject


def test_held_round_without_any_administrator_logs_a_warning(
    world, make_user, marco_api, complete_draft, caplog
):
    scenario_none_hold(world, make_user)
    with caplog.at_level(logging.WARNING):
        submit(marco_api, complete_draft()["reference"])
    assert "no active administrator" in caplog.text
    assert not EmailOutbox.objects.filter(template_key="approvalHeld").exists()


def test_skip_fallback_does_not_send_the_held_email(world, make_user, marco_api, complete_draft):
    scenario_none_skip(world, make_user)
    make_user("admin1@diasorin.com", admin=True)
    submit(marco_api, complete_draft()["reference"])
    assert not EmailOutbox.objects.filter(template_key="approvalHeld").exists()


# ------------------------------------------------------------------ 4 + 9: duplicate / visibility
def test_only_the_owner_can_duplicate_an_approver_gets_403_a_stranger_404(
    world, marco_api, complete_draft, make_user, sign_in
):
    ref = complete_draft()["reference"]
    submit(marco_api, ref)
    giulia = sign_in("g.ferrari@diasorin.com", client=APIClient())  # eligible approver: can view
    assert giulia.get(f"/api/requests/{ref}").status_code == 200
    assert giulia.post(f"/api/requests/{ref}/duplicate").status_code == 403
    make_user("stranger@diasorin.com")
    stranger = sign_in("stranger@diasorin.com", client=APIClient())
    assert stranger.post(f"/api/requests/{ref}/duplicate").status_code == 404
    assert marco_api.post(f"/api/requests/{ref}/duplicate").status_code == 201


def test_edit_endpoints_answer_404_to_strangers_and_403_to_viewers(
    world, marco_api, complete_draft, make_user, sign_in, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    ref = complete_draft()["reference"]
    submit(marco_api, ref)
    giulia = sign_in("g.ferrari@diasorin.com", client=APIClient())
    make_user("stranger@diasorin.com")
    stranger = sign_in("stranger@diasorin.com", client=APIClient())
    calls = [
        ("patch", f"/api/requests/{ref}/steps/1", {"version": "x"}),
        ("patch", f"/api/requests/{ref}/draft", {"version": "x"}),
        ("post", f"/api/requests/{ref}/discard", None),
        ("post", f"/api/requests/{ref}/submit", {"declaration": True}),
        ("post", f"/api/requests/{ref}/duplicate", None),
        ("delete", f"/api/requests/{ref}/attachments/1", None),
    ]
    for method, url, body in calls:
        assert getattr(stranger, method)(url, body, format="json").status_code == 404, url
        assert getattr(giulia, method)(url, body, format="json").status_code == 403, url
    assert upload_pdf(stranger, ref).status_code == 404
    assert upload_pdf(giulia, ref).status_code == 403
    assert stranger.get("/api/requests/DSF-2000-0001").status_code == 404  # unknown: same answer


# ------------------------------------------------------------------ 6: DRF's own messages in Italian
def test_builtin_validation_message_is_italian_for_italian_requests(marco_api, new_draft):
    d = new_draft()
    url = f"/api/requests/{d['reference']}/draft"
    body = {"version": d["version"], "ship_day_requested": "not-a-date"}
    en = marco_api.patch(url, body, format="json", headers={"Accept-Language": "en"}).json()
    it = marco_api.patch(url, body, format="json", headers={"Accept-Language": "it"}).json()
    assert "wrong format" in str(en).lower()
    assert "wrong format" not in str(it).lower() and str(it) != str(en)


# ------------------------------------------------------------------ 7: CSV labels
@pytest.mark.parametrize(
    "lang,header,status,approval",
    [
        ("en", "Reference", "Pending approval", "Pending · Giulia Ferrari"),
        ("it", "Riferimento", "In attesa di approvazione", "In attesa · Giulia Ferrari"),
    ],
)
def test_csv_writes_labels_in_the_request_language(
    world, marco_api, complete_draft, lang, header, status, approval
):
    submit(marco_api, complete_draft()["reference"])
    resp = marco_api.get("/api/requests/export.csv", headers={"Accept-Language": lang})
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert rows[0][0] == header and len(rows[0]) == 13
    assert rows[1][-1] == status and rows[1][-2] == approval


# ------------------------------------------------------------------ 8: attachments
def test_download_keeps_non_ascii_file_names(marco_api, new_draft, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    ref = new_draft()["reference"]
    att = upload_pdf(marco_api, ref, "certificato_già.pdf").json()
    got = marco_api.get(f"/api/requests/{ref}/attachments/{att['id']}")
    b"".join(got.streaming_content)
    assert got.status_code == 200
    assert got["Content-Disposition"].startswith("attachment")
    assert "certificato_gi%C3%A0.pdf" in got["Content-Disposition"]


def test_delete_unknown_attachment_is_404_and_the_file_goes_only_on_commit(
    marco_api, new_draft, settings, tmp_path, django_capture_on_commit_callbacks
):
    settings.MEDIA_ROOT = tmp_path
    ref = new_draft()["reference"]
    assert marco_api.delete(f"/api/requests/{ref}/attachments/99999").status_code == 404
    att = upload_pdf(marco_api, ref).json()
    path = Attachment.objects.get(pk=att["id"]).file.path
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert marco_api.delete(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 204
    assert os.path.exists(path)  # nothing removed before the commit
    for cb in callbacks:
        cb()
    assert not os.path.exists(path)


# ------------------------------------------------------------------ list/CSV: Skipped vs Not required, request id
def test_exempt_requester_shows_skipped_and_switched_off_shows_not_required(
    world, make_user, marco_api, complete_draft
):
    scenario_global_off(world, make_user)
    submit(marco_api, complete_draft()["reference"])
    assert marco_api.get("/api/requests").json()["results"][0]["approval"]["state"] == "NOT_REQUIRED"
    world["marco"].approval_exempt = True
    world["marco"].save()
    SiteConfig.objects.update(approval_global_enabled=True)
    submit(marco_api, complete_draft()["reference"])
    rows = marco_api.get("/api/requests").json()["results"]
    assert rows[0]["approval"]["state"] == "SKIPPED"
    csv_text = marco_api.get("/api/requests/export.csv", headers={"Accept-Language": "it"}).content.decode(
        "utf-8-sig"
    )
    assert "Saltata" in csv_text


def test_every_response_carries_a_request_id(api):
    r = api.get("/api/public/site")
    assert len(r["X-Request-ID"]) >= 8
    assert api.get("/api/public/site", headers={"X-Request-ID": "abc123"})["X-Request-ID"] == "abc123"
