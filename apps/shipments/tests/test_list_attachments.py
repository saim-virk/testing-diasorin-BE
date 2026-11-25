"""My requests (DSF-04.02), attachments, master-data endpoints and error messages."""

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.shipments.enums import Status
from apps.shipments.models import ShipmentRequest

pytestmark = pytest.mark.django_db

STATUS_LABEL = dict(Status.choices)

ALL_STATUSES = [
    "DRAFT", "PENDING_APPROVAL", "REJECTED", "TO_VERIFY", "RETURNED", "VERIFIED", "PACKED", "IN_TRANSIT", "DELIVERED", "CANCELLED",
]  # fmt: skip


@pytest.fixture
def one_per_status(world, marco_api, new_draft, payloads):
    refs = {}
    for status in ALL_STATUSES:
        d = new_draft(destination="ITALY")
        ShipmentRequest.objects.filter(reference=d["reference"]).update(status=status)
        refs[status] = d["reference"]
    return refs


def refs_of(resp):
    return {r["reference"] for r in resp.json()["results"]}


@pytest.mark.parametrize(
    "chip,statuses",
    [
        ("all", ALL_STATUSES),
        ("open", [s for s in ALL_STATUSES if s not in ("DELIVERED", "CANCELLED")]),
        ("attention", ["DRAFT", "REJECTED", "RETURNED"]),
        ("drafts", ["DRAFT"]),
        ("closed", ["DELIVERED", "CANCELLED"]),
    ],
)
def test_each_filter_returns_exactly_its_statuses(marco_api, one_per_status, chip, statuses):
    r = marco_api.get(f"/api/requests?scope=mine&filter={chip}")
    assert refs_of(r) == {one_per_status[s] for s in statuses}


def test_status_param_and_unknown_values(marco_api, one_per_status):
    r = marco_api.get("/api/requests?status=DRAFT,CANCELLED")
    assert refs_of(r) == {one_per_status["DRAFT"], one_per_status["CANCELLED"]}
    assert marco_api.get("/api/requests?status=NOPE").status_code == 400
    assert marco_api.get("/api/requests?filter=nope").status_code == 400
    assert marco_api.get("/api/requests?scope=all").status_code == 400
    assert marco_api.get("/api/requests?sort=nope").status_code == 400


def test_list_shows_only_my_requests(world, marco_api, new_draft, make_user, sign_in):
    mine = new_draft()
    make_user("other@diasorin.com")
    other = sign_in("other@diasorin.com", client=APIClient())
    other.post("/api/requests", {}, format="json")
    assert refs_of(marco_api.get("/api/requests")) == {mine["reference"]}


def test_search_on_pvari_code_description_recipient_cost_centre_and_status(
    marco_api, complete_draft, new_draft, payloads
):
    a = complete_draft(
        lines=[payloads.line(pvari_code="P9902", temperature="COOL_2_8", description="Zebra reagent")],
        dangerous_features="INFECTIOUS",
    )
    b = complete_draft(consignee_company="Clinica Alfa")
    c = new_draft()
    assert refs_of(marco_api.get("/api/requests?q=P9902")) == {a["reference"]}  # AC-04.02.2
    assert refs_of(marco_api.get("/api/requests?q=zebra")) == {a["reference"]}
    assert refs_of(marco_api.get("/api/requests?q=alfa")) == {b["reference"]}
    assert refs_of(marco_api.get("/api/requests?q=DS-IT-SAL")) == {a["reference"], b["reference"]}
    assert refs_of(marco_api.get("/api/requests?q=CC-4410")) >= {a["reference"], b["reference"]}
    assert c["reference"] in refs_of(marco_api.get("/api/requests?q=draft"))
    assert refs_of(marco_api.get(f"/api/requests?q={a['reference']}")) == {a["reference"]}
    assert refs_of(marco_api.get("/api/requests?q=nothing-matches-this")) == set()


def test_sorting_by_reference_and_ship_day(marco_api, new_draft):
    first, second = new_draft(), new_draft()
    marco_api.patch(
        f"/api/requests/{first['reference']}/draft",
        {"version": first["version"], "ship_day_requested": "2099-01-02"},
        format="json",
    )
    marco_api.patch(
        f"/api/requests/{second['reference']}/draft",
        {"version": second["version"], "ship_day_requested": "2099-01-01"},
        format="json",
    )
    order = lambda s: [r["reference"] for r in marco_api.get(f"/api/requests?sort={s}").json()["results"]]  # noqa: E731
    assert order("reference") == [first["reference"], second["reference"]]
    assert order("-reference") == [second["reference"], first["reference"]]
    assert order("ship_day") == [second["reference"], first["reference"]]
    assert order("-ship_day") == [first["reference"], second["reference"]]


def test_rows_carry_the_approval_summary(world, marco_api, complete_draft):
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    row = marco_api.get("/api/requests").json()["results"][0]
    assert row["approval"] == {"state": "PENDING", "names": ["Giulia Ferrari"]}
    assert row["line_count"] == 1 and row["pvari_codes"] == ["P9993"] and row["total_weight_kg"] == "1.200"


def test_csv_has_the_same_rows_and_columns_as_the_filtered_list(marco_api, one_per_status):
    for query in ("filter=attention", "q=DS-IT&sort=-reference", ""):
        listed = marco_api.get(f"/api/requests?{query}").json()["results"]
        resp = marco_api.get(f"/api/requests/export.csv?{query}")
        assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        assert [r[0] for r in rows[1:]] == [r["reference"] for r in listed]  # same rows, same order
        assert rows[0][:2] == ["Reference", "Created"] and rows[0][-1] == "Status" and len(rows[0]) == 13
        assert [r[-1] for r in rows[1:]] == [STATUS_LABEL[r["status"]] for r in listed]  # labels, not codes


def test_csv_neutralises_formulas(marco_api, new_draft):
    d = new_draft()
    marco_api.patch(
        f"/api/requests/{d['reference']}/draft",
        {"version": d["version"], "consignee_company": "=HYPERLINK(1)"},
        format="json",
    )
    text = marco_api.get("/api/requests/export.csv").content.decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in text


def test_csv_export_route_exists_next_to_the_json_one(marco_api):
    assert marco_api.get("/api/requests/export.csv").status_code == 200


# ------------------------------------------------------------------ attachments
def upload(client, ref, name, content, kind="MSDS"):
    f = SimpleUploadedFile(name, content)
    return client.post(f"/api/requests/{ref}/attachments", {"kind": kind, "file": f}, format="multipart")


def test_attachment_type_and_size_limits(marco_api, new_draft, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    ref = new_draft()["reference"]
    assert upload(marco_api, ref, "a.pdf", b"%PDF-1.4 ok").status_code == 201
    assert upload(marco_api, ref, "a.png", b"\x89PNG\r\n\x1a\n....", "COA").status_code == 201
    assert upload(marco_api, ref, "a.jpg", b"\xff\xd8\xff\xe0..", "OTHER").status_code == 201
    assert upload(marco_api, ref, "a.docx", b"PK\x03\x04....").status_code == 201
    assert upload(marco_api, ref, "a.xlsx", b"PK\x03\x04....").status_code == 201
    assert upload(marco_api, ref, "virus.exe", b"MZ....").status_code == 400
    assert (
        upload(marco_api, ref, "fake.pdf", b"MZ not a pdf").status_code == 400
    )  # content must match the type
    assert upload(marco_api, ref, "empty.pdf", b"").status_code == 400
    assert upload(marco_api, ref, "a.pdf", b"x", "BOGUS").status_code == 400
    big = b"%PDF" + b"0" * (20 * 1024 * 1024)
    assert upload(marco_api, ref, "big.pdf", big).status_code == 400
    assert upload(marco_api, ref, "exact.pdf", b"%PDF" + b"0" * (20 * 1024 * 1024 - 4)).status_code == 201


def test_attachment_download_delete_and_visibility(
    marco_api, new_draft, make_user, sign_in, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    ref = new_draft()["reference"]
    att = upload(marco_api, ref, "../../evil name.pdf", b"%PDF-1.4 content").json()
    assert att["original_name"] == "evil name.pdf"  # path stripped
    got = marco_api.get(f"/api/requests/{ref}/attachments/{att['id']}")
    assert got.status_code == 200 and b"".join(got.streaming_content) == b"%PDF-1.4 content"
    assert got["X-Content-Type-Options"] == "nosniff"

    make_user("stranger@diasorin.com")
    stranger = sign_in("stranger@diasorin.com", client=APIClient())
    assert stranger.get(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 404
    assert upload(stranger, ref, "x.pdf", b"%PDF-1.4 x").status_code == 404
    assert stranger.delete(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 404
    cm = make_user("cm@diasorin.com", customer_management=True)
    cm_client = sign_in(cm.email, client=APIClient())
    assert (
        cm_client.get(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 404
    )  # drafts: owner only
    ShipmentRequest.objects.filter(reference=ref).update(status="TO_VERIFY", submitted_at=timezone.now())
    seen = cm_client.get(f"/api/requests/{ref}/attachments/{att['id']}")  # customer management may see it
    assert seen.status_code == 200 and b"".join(
        seen.streaming_content
    )  # consumed: Windows keeps open files locked
    ShipmentRequest.objects.filter(reference=ref).update(status="DRAFT", submitted_at=None)

    assert marco_api.delete(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 204
    assert marco_api.get(f"/api/requests/{ref}/attachments/{att['id']}").status_code == 404


def test_attachments_cannot_be_changed_after_submit(world, marco_api, complete_draft, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert upload(marco_api, d["reference"], "a.pdf", b"%PDF-1.4 x").status_code == 409


# ------------------------------------------------------------------ master data
def test_master_data_endpoints_need_sign_in_and_filter_by_destination(world, api, marco_api, reason_it):
    anon = APIClient()
    for path in (
        "branches",
        "reason-codes",
        "countries",
        "pvari",
        "currencies",
        "packaging",
        "carriers",
        "ships-from",
        "cost-centres",
    ):
        assert anon.get(f"/api/masterdata/{path}").status_code == 401, path

    codes = lambda p: [r["code"] for r in marco_api.get(f"/api/masterdata/{p}").json()]  # noqa: E731
    assert codes("branches?destination=EU") == ["DS-DE-DIE"]
    assert codes("branches?destination=USA") == ["DS-US-AUS", "DS-US-STW"]
    assert len(codes("reason-codes?destination=ITALY")) == 11  # AC-03.04.1
    for dest in ("EU", "EXTRA_EU", "USA"):
        assert len(codes(f"reason-codes?destination={dest}")) == 11
    assert [c["iso2"] for c in marco_api.get("/api/masterdata/countries?destination=ITALY").json()] == ["IT"]
    assert [c["iso2"] for c in marco_api.get("/api/masterdata/countries?destination=USA").json()] == ["US"]
    eu = [c["iso2"] for c in marco_api.get("/api/masterdata/countries?destination=EU").json()]
    assert "DE" in eu and "IT" not in eu and "US" not in eu
    assert marco_api.get("/api/masterdata/branches?destination=MARS").status_code == 400
    assert len(codes("pvari")) == 11 and len(codes("currencies")) == 14
    assert len(marco_api.get("/api/masterdata/carriers").json()) == 5


def test_master_data_hides_inactive_rows_and_ships_from_carries_the_calendar(marco_api):
    from apps.masterdata.models import Branch, PVARICode

    PVARICode.objects.filter(code="P9993").update(is_active=False)
    assert "P9993" not in [r["code"] for r in marco_api.get("/api/masterdata/pvari").json()]
    Branch.objects.filter(code="DS-IT-SAL").update(is_active=False)
    assert marco_api.get("/api/masterdata/branches?destination=ITALY").json() == []
    sites = {s["code"]: s for s in marco_api.get("/api/masterdata/ships-from").json()}
    assert (
        sites["SALUGGIA"]["allowed_weekdays"] == [0, 1, 2, 3]
        and sites["SALUGGIA"]["hint"] == "Saluggia ships Mon, Tue, Wed, Thu."
    )
    assert sites["GERENZANO"]["applies_calendar"] is False and sites["GERENZANO"]["hint"] is None
    assert marco_api.get("/api/masterdata/currencies").json()[0] == {"code": "EUR"}
    assert marco_api.get("/api/masterdata/packaging").json()[0].keys() == {
        "code",
        "dimensions",
        "description",
    }


# ------------------------------------------------------------------ error messages (EN / IT)
def test_every_error_carries_a_message_in_the_requests_language(marco_api, new_draft, payloads):
    d = new_draft()
    body = {**payloads.step1(applicant_name=""), "version": d["version"]}
    en = marco_api.patch(f"/api/requests/{d['reference']}/steps/1", body, format="json")
    assert en.json()["message"] == "Please correct the highlighted fields."
    assert en.json()["errors"]["applicant_name"] == ["Applicant is mandatory."]
    it = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1", body, format="json", headers={"Accept-Language": "it"}
    )
    assert it.json()["message"] == "Correggi i campi evidenziati."
    assert it.json()["errors"]["applicant_name"] == ["Il richiedente è obbligatorio."]

    stale = marco_api.patch(
        f"/api/requests/{d['reference']}/draft",
        {"version": "2000-01-01T00:00:00Z"},
        format="json",
        headers={"Accept-Language": "it"},
    )
    assert stale.status_code == 409 and "Ricarica" in stale.json()["message"]
    assert (
        "Reload"
        in marco_api.patch(
            f"/api/requests/{d['reference']}/draft", {"version": "2000-01-01T00:00:00Z"}, format="json"
        ).json()["message"]
    )


def test_profile_language_is_used_without_a_header(world, marco_api, new_draft):
    world["marco"].language = "it"
    world["marco"].save()
    d = new_draft()
    r = marco_api.patch(f"/api/requests/{d['reference']}/steps/1", {"version": d["version"]}, format="json")
    assert r.json()["message"] == "Correggi i campi evidenziati."


def test_403_404_and_401_bodies_have_a_message(world, marco_api):
    assert marco_api.get("/api/requests/DSF-1999-0001").json()["message"]
    assert APIClient().get("/api/requests").json()["message"]
