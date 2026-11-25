"""Day 3 independent review fixes (Fable review 2026-11-23): one test per finding that failed before its fix."""

import csv
import io

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.notifications.models import EmailOutbox
from apps.shipments.models import ShipmentRequest

pytestmark = pytest.mark.django_db


def submit(client, ref):
    return client.post(f"/api/requests/{ref}/submit", {"declaration": True}, format="json")


def returned_after(world, marco_api, complete_draft, round_state):
    """A submitted request whose round ended as `round_state`, now sent back to the requester."""
    d = complete_draft()
    assert submit(marco_api, d["reference"]).status_code == 200
    req = ShipmentRequest.objects.get(reference=d["reference"])
    rnd = req.approval_rounds.get()
    rnd.state = round_state
    rnd.save()
    req.status = "RETURNED"
    req.save()
    return d["reference"]


# ------------------------------------------------------------------ 1: first Save draft with empty rows
def test_first_save_with_empty_lines_and_parcels_creates_the_draft(marco_api):
    r = marco_api.post("/api/requests", {"lines": [], "parcels": []}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["lines"] == [] and r.json()["parcels"] == []


def test_first_save_with_one_line_and_one_parcel_keeps_them(marco_api, payloads):
    body = {"lines": [payloads.line()], "parcels": [{"count": 1, "gross_weight_kg": "2"}]}
    r = marco_api.post("/api/requests", body, format="json")
    assert r.status_code == 201, r.content
    assert len(r.json()["lines"]) == 1 and len(r.json()["parcels"]) == 1


# ------------------------------------------------------------------ 4: what happens next after a skipped re-approval
@pytest.mark.parametrize(
    "round_state,why,note",
    [
        ("APPROVED", "approval_already_given", "APPROVAL_ALREADY_GIVEN"),
        ("NOT_REQUIRED", "no_approval_needed", "NOT_NEEDED"),
    ],
)
def test_returned_resubmit_that_skips_reapproval_says_so_everywhere(
    world, marco_api, complete_draft, round_state, why, note, settings
):
    ref = returned_after(world, marco_api, complete_draft, round_state)
    EmailOutbox.objects.all().delete()

    hint = marco_api.get(f"/api/requests/{ref}").json()["routing_hint"]  # step 2 / step 5
    assert (hint["required"], hint["why"], hint["approvers"]) == (False, why, [])

    body = submit(marco_api, ref).json()
    assert body["status"] == "TO_VERIFY"
    nxt = body["next_steps"]  # confirmation page
    assert (nxt["approval_required"], nxt["approvers"], nxt["approval_note"]) == (False, [], note)

    mail = EmailOutbox.objects.get(template_key="oeNew")  # email to customer management
    expected = "approval already given" if round_state == "APPROVED" else "no approval needed"
    assert expected in mail.subject + mail.body
    assert not EmailOutbox.objects.filter(template_key="approvalRequired").exists()


def test_returned_with_a_changed_cost_centre_is_routed_again(world, make_user, marco_api, complete_draft):
    from apps.masterdata.models import CostCentre

    make_user("admin@diasorin.com", admin=True)  # CC-9999 has no approver: the admin fallback needs someone
    CostCentre.objects.create(code="CC-9999", name="Other", approval_required=True)
    ref = returned_after(world, marco_api, complete_draft, "APPROVED")
    req = ShipmentRequest.objects.get(reference=ref)
    marco_api.patch(
        f"/api/requests/{ref}/draft",
        {"version": marco_api.get(f"/api/requests/{ref}").json()["version"], "cost_centre_code": "CC-9999"},
        format="json",
    )
    assert (
        marco_api.get(f"/api/requests/{ref}").json()["routing_hint"] is None
    )  # the centre's own hint applies
    body = submit(marco_api, ref).json()
    assert body["status"] == "PENDING_APPROVAL" and body["next_steps"]["approval_required"] is True
    assert req.approval_rounds.count() == 2


# ------------------------------------------------------------------ 5: CSV labels for scope and temperature
@pytest.mark.parametrize(
    "lang,scope,temp",
    [("en", "Extra-EU", "+2 +8 °C"), ("it", "Extra-UE", "+2 +8 °C")],
)
def test_csv_writes_scope_and_temperature_labels(marco_api, complete_draft, lang, scope, temp):
    d = complete_draft(destination="EXTRA_EU")
    rows = list(
        csv.reader(
            io.StringIO(
                marco_api.get("/api/requests/export.csv", headers={"Accept-Language": lang}).content.decode(
                    "utf-8-sig"
                )
            )
        )
    )
    row = next(r for r in rows[1:] if r[0] == d["reference"])
    assert row[4] == scope and row[9] == temp


def test_csv_italian_temperature_and_scope_names(marco_api, complete_draft, payloads):
    complete_draft(lines=[payloads.line(temperature="AMBIENT")])
    text = marco_api.get("/api/requests/export.csv", headers={"Accept-Language": "it"}).content.decode(
        "utf-8-sig"
    )
    row = list(csv.reader(io.StringIO(text)))[1]
    assert row[4] == "Italia" and row[9] == "Ambiente"


# ------------------------------------------------------------------ 6: Italian status names in the search
def test_search_matches_italian_status_labels(marco_api, new_draft):
    draft = new_draft()
    other = new_draft()
    ShipmentRequest.objects.filter(reference=other["reference"]).update(status="IN_TRANSIT")
    refs = lambda q: [r["reference"] for r in marco_api.get("/api/requests", {"q": q}).json()["results"]]  # noqa: E731
    assert refs("Bozza") == [draft["reference"]]
    assert refs("In transito") == [other["reference"]]


# ------------------------------------------------------------------ 7: Italian 409 names the status in Italian
def test_italian_409_translates_the_status_label(world, marco_api, complete_draft):
    ref = complete_draft()["reference"]
    submit(marco_api, ref)
    version = marco_api.get(f"/api/requests/{ref}").json()["version"]
    r = marco_api.patch(
        f"/api/requests/{ref}/draft", {"version": version}, format="json", headers={"Accept-Language": "it"}
    )
    assert r.status_code == 409
    assert "«In attesa di approvazione»" in r.json()["message"]
    assert "Pending approval" not in r.json()["message"]


# ------------------------------------------------------------------ 8: drafts are visible to their owner only
@pytest.mark.parametrize(
    "flags", [{"customer_management": True}, {"admin": True}], ids=["customer_mgmt", "admin"]
)
def test_staff_cannot_see_a_never_submitted_draft(
    world, make_user, sign_in, marco_api, complete_draft, flags
):
    ref = complete_draft()["reference"]
    make_user("staff@diasorin.com", **flags)
    staff = sign_in("staff@diasorin.com", client=APIClient())
    assert staff.get(f"/api/requests/{ref}").status_code == 404
    assert submit(marco_api, ref).status_code == 200
    assert staff.get(f"/api/requests/{ref}").status_code == 200


# ------------------------------------------------------------------ 10: reference year follows Rome
def test_reference_year_uses_the_rome_date(world, sign_in):
    with freeze_time("2026-12-31 23:30:00"):  # 00:30 on 1 January in Rome
        client = sign_in("m.rossi@diasorin.com", client=APIClient())
        d = client.post("/api/requests", {}, format="json").json()
        assert d["reference"].startswith("DSF-2027-")
        copy = client.post(f"/api/requests/{d['reference']}/duplicate").json()
        assert copy["reference"].startswith("DSF-2027-")


# ------------------------------------------------------------------ 11: quantity, unit and lot are separate fields
def line_errors(marco_api, d, line):
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/3",
        {
            "version": d["version"],
            "lines": [line],
            "dangerous_features": "UNINFECTED",
            "material_type": "IVD",
        },
        format="json",
    )
    assert r.status_code == 400, r.content
    return r.json()["errors"]["lines"]["0"]


def test_quantity_unit_and_lot_have_their_own_errors(marco_api, new_draft, payloads):
    d = new_draft()
    errs = line_errors(marco_api, d, payloads.line(quantity=None, uom=None, lot_number=None))
    assert errs["quantity"] == ["Quantity is mandatory."]
    assert errs["uom"] == ["Choose a unit."]
    assert errs["lot_number"] == ["Lot / batch is mandatory for PVARI lines."]
    assert line_errors(marco_api, d, payloads.line(quantity="0"))["quantity"] == [
        "Enter a number greater than 0."
    ]


def test_other_unit_needs_the_typed_text_and_a_typed_unit_is_kept(marco_api, new_draft, payloads):
    d = new_draft()
    assert line_errors(marco_api, d, payloads.line(uom="other"))["uom"] == ["Choose a unit."]
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/3",
        {"version": d["version"], "lines": [payloads.line(uom="carton")], "dangerous_features": "UNINFECTED",
         "material_type": "IVD"},
        format="json",
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["lines"][0]["uom"] == "carton"


def test_italian_unit_and_lot_messages(marco_api, new_draft, payloads):
    d = new_draft()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/3",
        {"version": d["version"], "lines": [payloads.line(uom=None, lot_number=None)],
         "dangerous_features": "UNINFECTED", "material_type": "IVD"},
        format="json", headers={"Accept-Language": "it"},
    )  # fmt: skip
    errs = r.json()["errors"]["lines"]["0"]
    assert errs["uom"] == ["Scegli un'unità di misura."]
    assert errs["lot_number"] == ["Il lotto è obbligatorio per le righe PVARI."]
