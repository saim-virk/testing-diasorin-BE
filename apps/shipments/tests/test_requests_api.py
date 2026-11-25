"""Request API: saving (Continue / Save draft), per-step validation, permissions, discard, duplicate, derived values."""

from datetime import timedelta

import pytest

from apps.masterdata.models import Branch, CostCentre, PVARICode, ShipsFromSite
from apps.platform_config.models import SiteConfig
from apps.shipments.models import RequestEvent, ShipmentRequest
from apps.shipments.services.validation import today_rome

from .conftest import day_on

pytestmark = pytest.mark.django_db


def errors_of(resp):
    assert resp.status_code == 400, resp.content
    return resp.json()["errors"]


# ------------------------------------------------------------------ drafts
def test_draft_with_nothing_and_with_only_a_destination(marco_api):
    r = marco_api.post("/api/requests", {}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["reference"].startswith("DSF-") and body["status"] == "DRAFT"
    assert (
        body["applicant_name"] == "Marco Rossi" and body["cost_centre_code"] == "CC-4410"
    )  # profile pre-fill
    r2 = marco_api.post("/api/requests", {"destination": "EU"}, format="json")
    assert r2.status_code == 201 and r2.json()["destination"] == "EU"
    assert r2.json()["reference"] != body["reference"]


def test_save_draft_accepts_anything_without_validation(marco_api, new_draft):
    d = new_draft()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/draft",
        {
            "version": d["version"],
            "consignee_phone": "not a phone",
            "consignee_email": "nope",
            "recipient_code": "MADE-UP",
            "reason_code": "99",
            "ship_day_requested": (today_rome() - timedelta(days=3)).isoformat(),
            "lines": [{"description": "half a line"}],
        },
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recipient_code"] == "MADE-UP" and body["lines"][0]["description"] == "half a line"


def test_first_continue_creates_the_draft_only_when_step1_is_valid(marco_api, payloads):
    bad = marco_api.post("/api/requests", {"step": 1, **payloads.step1(applicant_name="")}, format="json")
    assert bad.status_code == 400 and bad.json()["step"] == 1 and "applicant_name" in bad.json()["errors"]
    assert ShipmentRequest.objects.count() == 0  # nothing created, no number burnt
    ok = marco_api.post("/api/requests", {"step": 1, **payloads.step1()}, format="json")
    assert ok.status_code == 201 and ok.json()["reference"].endswith("-0001")


def test_continue_validates_only_its_own_step(marco_api, new_draft, save_step, payloads):
    d = new_draft()
    # step 2 is empty, but step 1 only checks step 1
    saved = save_step(d["reference"], 1, d["version"], payloads.step1())
    assert saved["destination"] == "ITALY"
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/2", {"version": saved["version"]}, format="json"
    )
    errs = errors_of(r)
    assert "recipient_code" in errs and "destination" not in errs and "applicant_name" not in errs
    assert r.json()["step"] == 2


def test_failed_continue_saves_nothing(marco_api, new_draft, payloads):
    d = new_draft()
    marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {"version": d["version"], **payloads.step1(ships_from_code="")},
        format="json",
    )
    assert ShipmentRequest.objects.get(reference=d["reference"]).destination is None


def test_a_field_of_another_step_is_refused_on_continue(marco_api, new_draft, payloads):
    d = new_draft()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {"version": d["version"], **payloads.step1(), "datalogger": "YES"},
        format="json",
    )
    assert "datalogger" in errors_of(r)


# ------------------------------------------------------------------ step 1 rules
@pytest.mark.parametrize(
    "field", ["destination", "applicant_name", "applicant_phone", "ships_from_code", "ship_day_requested"]
)
def test_step1_required_fields(marco_api, new_draft, payloads, field):
    d = new_draft()
    body = {**payloads.step1(), field: None, "version": d["version"]}
    r = marco_api.patch(f"/api/requests/{d['reference']}/steps/1", body, format="json")
    assert field in errors_of(r)


def test_step1_valid_passes(new_draft, save_step, payloads):
    d = new_draft()
    save_step(d["reference"], 1, d["version"], payloads.step1())


def test_saluggia_friday_rejected_gerenzano_accepted(marco_api, new_draft, payloads):
    d = new_draft()
    friday = day_on(4).isoformat()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {**payloads.step1(ship_day_requested=friday), "version": d["version"]},
        format="json",
    )
    assert "ship_day_requested" in errors_of(r) and "Saluggia ships Mon, Tue, Wed, Thu." in str(r.json())
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {
            **payloads.step1(ship_day_requested=day_on(5).isoformat(), ships_from_code="GERENZANO"),
            "version": d["version"],
        },
        format="json",
    )
    assert r.status_code == 200  # a Saturday from Gerenzano


def test_changing_the_saluggia_calendar_changes_the_allowed_days_immediately(marco_api, new_draft, payloads):
    d = new_draft()
    friday = payloads.step1(ship_day_requested=day_on(4).isoformat())
    site = ShipsFromSite.objects.get(code="SALUGGIA")
    site.allowed_weekdays = [0, 1, 2, 3, 4]
    site.save()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1", {**friday, "version": d["version"]}, format="json"
    )
    assert r.status_code == 200
    assert (
        "Fri"
        in next(s for s in marco_api.get("/api/masterdata/ships-from").json() if s["code"] == "SALUGGIA")[
            "hint"
        ]
    )


def test_past_dates_are_refused_for_any_warehouse_but_today_is_fine(marco_api, new_draft, payloads):
    d = new_draft()
    v = d["version"]
    for code in ("SALUGGIA", "GERENZANO", "OTHER"):
        yesterday = (today_rome() - timedelta(days=1)).isoformat()
        r = marco_api.patch(
            f"/api/requests/{d['reference']}/steps/1",
            {**payloads.step1(ships_from_code=code, ship_day_requested=yesterday), "version": v},
            format="json",
        )
        assert "ship_day_requested" in errors_of(r)
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {
            **payloads.step1(ships_from_code="OTHER", ship_day_requested=today_rome().isoformat()),
            "version": v,
        },
        format="json",
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    "phone,ok", [("+39 335 118 4402", True), ("(011) 555-1234", True), ("12345", False), ("abc123456", False)]
)
def test_phone_loose_check(marco_api, new_draft, payloads, phone, ok):
    d = new_draft()
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/steps/1",
        {**payloads.step1(applicant_phone=phone), "version": d["version"]},
        format="json",
    )
    assert (r.status_code == 200) is ok


# ------------------------------------------------------------------ step 2 rules
def _step2(marco_api, d, body):
    version = marco_api.get(f"/api/requests/{d['reference']}").json()["version"]
    return marco_api.patch(
        f"/api/requests/{d['reference']}/steps/2", {**body, "version": version}, format="json"
    )


@pytest.fixture
def italy_draft(new_draft):
    return new_draft(destination="ITALY")


@pytest.mark.parametrize(
    "field",
    [
        "recipient_code",
        "reason_code",
        "consignee_company",
        "consignee_first_name",
        "consignee_last_name",
        "consignee_street",
        "consignee_postal_code",
        "consignee_city",
        "consignee_country_code",
        "consignee_phone",
        "cost_centre_code",
    ],
)
def test_step2_required_fields(marco_api, italy_draft, payloads, field):
    r = _step2(marco_api, italy_draft, {**payloads.step2(), field: ""})
    assert field in errors_of(r)


def test_step2_valid_passes_and_snapshots_labels(marco_api, italy_draft, payloads):
    r = _step2(marco_api, italy_draft, payloads.step2())
    assert r.status_code == 200
    body = r.json()
    assert body["recipient_branch_name"] == "Diasorin Italia — Saluggia"
    assert body["cost_centre_name"] == "Warehouse" and body["consignee_country_name"] == "Italy"
    assert body["reason_label_it"] and body["reason_label_en"]


def test_optional_step2_fields_may_be_empty_and_bad_email_is_refused(marco_api, italy_draft, payloads):
    assert _step2(marco_api, italy_draft, payloads.step2(consignee_email="")).status_code == 200
    r = _step2(marco_api, italy_draft, payloads.step2(consignee_email="not-an-email"))
    assert "consignee_email" in errors_of(r)


def test_recipient_branch_scope_must_match_destination(marco_api, italy_draft, payloads):
    r = _step2(marco_api, italy_draft, payloads.step2(recipient_code="DS-DE-DIE"))
    assert "recipient_code" in errors_of(r)


def test_inactive_branch_is_not_a_valid_recipient(marco_api, italy_draft, payloads):
    Branch.objects.filter(code="DS-IT-SAL").update(is_active=False)
    assert "recipient_code" in errors_of(_step2(marco_api, italy_draft, payloads.step2()))


def test_eu_request_with_the_italian_reason_code_is_refused(marco_api, new_draft, payloads):
    d = new_draft(destination="EU")
    eu = payloads.step2(
        recipient_code="DS-DE-DIE", consignee_country_code="DE", reason_code=payloads.reason_it
    )
    assert "reason_code" in errors_of(_step2(marco_api, d, eu))
    assert _step2(marco_api, d, {**eu, "reason_code": payloads.reason_eu}).status_code == 200


def test_italy_reason_code_on_an_italian_destination_and_eu_code_refused(marco_api, italy_draft, payloads):
    r = _step2(marco_api, italy_draft, payloads.step2(reason_code=payloads.reason_eu))
    assert "reason_code" in errors_of(r)


def test_country_is_pick_only_and_fixed_for_italy_and_usa(marco_api, new_draft, italy_draft, payloads):
    assert "consignee_country_code" in errors_of(
        _step2(marco_api, italy_draft, payloads.step2(consignee_country_code="DE"))
    )
    assert "consignee_country_code" in errors_of(
        _step2(marco_api, italy_draft, payloads.step2(consignee_country_code="Narnia"))
    )
    us = new_draft(destination="USA")
    body = payloads.step2(
        recipient_code="DS-US-AUS", reason_code=payloads.reason_eu, consignee_country_code="CA"
    )
    assert "consignee_country_code" in errors_of(_step2(marco_api, us, body))
    assert _step2(marco_api, us, {**body, "consignee_country_code": "US"}).status_code == 200
    eu = new_draft(destination="EU")
    eu_body = payloads.step2(recipient_code="DS-DE-DIE", reason_code=payloads.reason_eu)
    assert "consignee_country_code" in errors_of(
        _step2(marco_api, eu, {**eu_body, "consignee_country_code": "IT"})
    )
    assert _step2(marco_api, eu, {**eu_body, "consignee_country_code": "FR"}).status_code == 200


def test_inactive_cost_centre_refused(marco_api, italy_draft, payloads):
    CostCentre.objects.filter(code="CC-4410").update(is_active=False)
    assert "cost_centre_code" in errors_of(_step2(marco_api, italy_draft, payloads.step2()))


def test_po_required_only_for_flagged_branch_and_when_the_rule_is_on(marco_api, new_draft, payloads):
    d = new_draft(destination="USA")
    base = payloads.step2(reason_code=payloads.reason_eu, consignee_country_code="US")
    stw = {**base, "recipient_code": "DS-US-STW"}
    assert "po_number" in errors_of(_step2(marco_api, d, stw))  # DS Inc without PO
    assert _step2(marco_api, d, {**stw, "po_number": "PO-1"}).status_code == 200
    # another USA branch is not flagged: PO optional
    assert _step2(marco_api, d, {**base, "recipient_code": "DS-US-AUS"}).status_code == 200
    # the Admin rule off: optional for DS Inc too
    cfg = SiteConfig.load()
    cfg.po_mandatory_us = False
    cfg.save()
    assert _step2(marco_api, d, stw).status_code == 200


# ------------------------------------------------------------------ step 3 rules
def _step3(marco_api, d, body):
    version = marco_api.get(f"/api/requests/{d['reference']}").json()["version"]
    return marco_api.patch(
        f"/api/requests/{d['reference']}/steps/3", {**body, "version": version}, format="json"
    )


@pytest.fixture
def d3(new_draft):
    return new_draft(destination="ITALY")


def test_step3_valid_passes_and_fills_derived(marco_api, d3, payloads):
    r = _step3(marco_api, d3, payloads.step3())
    assert r.status_code == 200
    body = r.json()
    assert (
        body["derived"]["overall_temperature"] == "COOL_2_8" and body["derived"]["total_weight_kg"] == "1.200"
    )
    assert body["lines"][0]["hazard"] == "UNINFECTED"


def test_at_least_one_line(marco_api, d3, payloads):
    assert "lines" in errors_of(_step3(marco_api, d3, payloads.step3(lines=[])))


@pytest.mark.parametrize(
    "field",
    [
        "lot_number",
        "net_weight_kg",
        "standard_price",
        "currency",
        "country_of_origin",
        "temperature",
        "description",
        "quantity",
        "uom",
    ],
)
def test_pvari_line_required_columns(marco_api, d3, payloads, field):
    r = _step3(marco_api, d3, payloads.step3(lines=[payloads.line(**{field: None})]))
    assert field in errors_of(r)["lines"]["0"]


def test_free_text_line_needs_quantity_but_not_the_pvari_columns(marco_api, d3, payloads):
    free = {"description": "Spare part", "quantity": "2", "uom": "pcs", "temperature": "AMBIENT"}
    r = _step3(marco_api, d3, payloads.step3(lines=[free]))
    assert r.status_code == 200
    no_qty = {**free, "quantity": None}
    assert "quantity" in errors_of(_step3(marco_api, d3, payloads.step3(lines=[no_qty])))["lines"]["0"]


def test_free_text_line_ignores_and_clears_the_na_columns(marco_api, d3, payloads):
    free = {
        "description": "Spare part",
        "quantity": "2",
        "uom": "pcs",
        "temperature": "AMBIENT",
        "net_weight_kg": "9",
        "currency": "EUR",
    }
    body = _step3(marco_api, d3, payloads.step3(lines=[free])).json()
    assert body["lines"][0]["net_weight_kg"] is None and body["lines"][0]["currency"] is None


def test_unknown_pvari_code_refused(marco_api, d3, payloads):
    r = _step3(marco_api, d3, payloads.step3(lines=[payloads.line(pvari_code="P0000")]))
    assert "pvari_code" in errors_of(r)["lines"]["0"]


def test_infectious_pvari_locks_dangerous_features(marco_api, d3, payloads):
    lines = [payloads.line(pvari_code="P9996", temperature="DRY_ICE")]
    for wrong in ("OTHER", "UNINFECTED"):
        r = _step3(
            marco_api, d3, payloads.step3(lines=lines, dangerous_features=wrong, other_hazard_text="x")
        )
        assert "dangerous_features" in errors_of(r)
    ok = _step3(marco_api, d3, payloads.step3(lines=lines, dangerous_features="INFECTIOUS"))
    assert ok.status_code == 200 and ok.json()["derived"]["dangerous_features_locked"] is True


def test_other_hazards_needs_text_and_msds(marco_api, d3, payloads, tmp_path):
    body = payloads.step3(dangerous_features="OTHER")
    errs = errors_of(_step3(marco_api, d3, body))
    assert "other_hazard_text" in errs and "attachments" in errs
    pdf = tmp_path / "msds.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    with pdf.open("rb") as fh:
        up = marco_api.post(
            f"/api/requests/{d3['reference']}/attachments", {"kind": "MSDS", "file": fh}, format="multipart"
        )
    assert up.status_code == 201
    fresh = marco_api.get(f"/api/requests/{d3['reference']}").json()
    ok = marco_api.patch(
        f"/api/requests/{d3['reference']}/steps/3",
        {**body, "other_hazard_text": "Corrosive", "version": fresh["version"]},
        format="json",
    )
    assert ok.status_code == 200


def test_msds_not_required_when_the_rule_is_off(marco_api, d3, payloads):
    cfg = SiteConfig.load()
    cfg.msds_required_other_hazard = False
    cfg.save()
    r = _step3(marco_api, d3, payloads.step3(dangerous_features="OTHER", other_hazard_text="Corrosive"))
    assert r.status_code == 200


def test_free_choice_without_pvari_lines(marco_api, d3, payloads):
    free = [{"description": "Spare part", "quantity": "2", "uom": "pcs", "temperature": "AMBIENT"}]
    for choice in ("UNINFECTED", "INFECTIOUS"):
        assert _step3(marco_api, d3, payloads.step3(lines=free, dangerous_features=choice)).status_code == 200


def test_material_type_other_needs_text(marco_api, d3, payloads):
    assert "material_type_other" in errors_of(_step3(marco_api, d3, payloads.step3(material_type="OTHER")))
    assert (
        _step3(
            marco_api, d3, payloads.step3(material_type="OTHER", material_type_other="Spare parts")
        ).status_code
        == 200
    )
    assert "material_type" in errors_of(_step3(marco_api, d3, payloads.step3(material_type=None)))


# ------------------------------------------------------------------ step 4 rules
def _step4(marco_api, d, body):
    version = marco_api.get(f"/api/requests/{d['reference']}").json()["version"]
    return marco_api.patch(
        f"/api/requests/{d['reference']}/steps/4", {**body, "version": version}, format="json"
    )


def test_step4_valid_and_datalogger_required(marco_api, new_draft, payloads):
    d = new_draft(destination="ITALY")
    assert _step4(marco_api, d, payloads.step4()).status_code == 200
    assert "datalogger" in errors_of(_step4(marco_api, d, payloads.step4(datalogger=None)))


def test_dedicated_transport_needs_a_note(marco_api, new_draft, payloads):
    d = new_draft(destination="ITALY")
    assert "dedicated_transport_note" in errors_of(
        _step4(marco_api, d, payloads.step4(dedicated_transport=True))
    )
    ok = _step4(
        marco_api, d, payloads.step4(dedicated_transport=True, dedicated_transport_note="World Courier")
    )
    assert ok.status_code == 200


def test_us_block_required_only_for_usa(marco_api, new_draft, payloads):
    it = new_draft(destination="ITALY")
    assert _step4(marco_api, it, payloads.step4()).status_code == 200
    us = new_draft(destination="USA")
    errs = errors_of(_step4(marco_api, us, payloads.step4()))
    assert {
        "us_usda_guideline",
        "us_usda_permit",
        "us_attach_000614",
        "us_cdc_permit",
        "us_importer_certification_statement",
    } <= set(errs)
    answers = {k: "NO" for k in errs}
    assert _step4(marco_api, us, payloads.step4(**answers)).status_code == 200


def test_usda_guideline_yes_needs_a_number(marco_api, new_draft, payloads):
    us = new_draft(destination="USA")
    answers = {
        k: "NO"
        for k in (
            "us_usda_permit",
            "us_attach_000614",
            "us_cdc_permit",
            "us_importer_certification_statement",
        )
    }
    body = payloads.step4(us_usda_guideline="YES", **answers)
    assert "us_usda_guideline_number" in errors_of(_step4(marco_api, us, body))
    assert _step4(marco_api, us, {**body, "us_usda_guideline_number": "G-77"}).status_code == 200


def test_parcel_rows_limited_and_packaging_fills_dimensions(marco_api, new_draft, payloads):
    d = new_draft(destination="ITALY")
    from apps.masterdata.models import PackagingType

    pack = PackagingType.objects.first()
    ok = _step4(marco_api, d, payloads.step4(parcels=[{"count": 1, "packaging_code": pack.code}]))
    assert ok.status_code == 200 and ok.json()["parcels"][0]["dimensions"] == (pack.dimensions or None)
    too_many = [{"count": 1}] * (SiteConfig.load().max_parcel_lines + 1)
    assert "parcels" in errors_of(_step4(marco_api, d, payloads.step4(parcels=too_many)))
    typed = _step4(
        marco_api,
        d,
        payloads.step4(parcels=[{"count": 1, "packaging_code": "MY-BOX", "dimensions": "1x1x1"}]),
    )
    assert typed.status_code == 200  # packaging is pick-or-type


# ------------------------------------------------------------------ derived values and snapshots
def test_strictest_temperature_and_deduplicated_un_numbers(marco_api, new_draft, payloads):
    d = new_draft(destination="ITALY")
    lines = [
        payloads.line(pvari_code="P9902", temperature="COOL_2_8"),
        payloads.line(pvari_code="P9902", temperature="AMBIENT"),
        payloads.line(pvari_code="P9996", temperature="DRY_ICE"),
        payloads.line(pvari_code="P9993", temperature="AMBIENT"),
    ]
    r = marco_api.patch(
        f"/api/requests/{d['reference']}/draft", {"lines": lines, "version": d["version"]}, format="json"
    )
    derived = r.json()["derived"]
    assert derived["overall_temperature"] == "DRY_ICE"
    assert derived["un_numbers"] == ["UN 2814"] and derived["hazard"] == "INFECTIOUS"
    assert derived["total_weight_kg"] == "4.800"
    assert r.json()["overall_temperature"] == "DRY_ICE"


def test_snapshots_do_not_change_when_a_pvari_row_is_edited_after_submit(marco_api, complete_draft, payloads):
    d = complete_draft(
        lines=[payloads.line(pvari_code="P9996", temperature="DRY_ICE")], dangerous_features="INFECTIOUS"
    )
    sub = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert sub.status_code == 200, sub.content
    PVARICode.objects.filter(code="P9996").update(un_number="UN 0000", hazard="UNINFECTED")
    line = marco_api.get(f"/api/requests/{d['reference']}").json()["lines"][0]
    assert line["un_number"] == "UN 2814" and line["hazard"] == "INFECTIOUS"


# ------------------------------------------------------------------ permissions and states
def test_non_owner_cannot_edit_and_gets_403(world, marco_api, new_draft, make_user, sign_in):
    from rest_framework.test import APIClient

    d = new_draft()
    make_user("other@diasorin.com")
    other = sign_in("other@diasorin.com", client=APIClient())
    r = other.patch(
        f"/api/requests/{d['reference']}/draft", {"version": d["version"], "notes": "x"}, format="json"
    )
    assert r.status_code == 404  # an unrelated user is not told the reference exists
    assert other.get(f"/api/requests/{d['reference']}").status_code == 404
    assert (
        other.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json").status_code
        == 404
    )
    assert other.post(f"/api/requests/{d['reference']}/discard").status_code == 404


def test_unauthenticated_calls_get_401(api):
    assert api.get("/api/requests").status_code == 401
    assert api.post("/api/requests", {}, format="json").status_code == 401


def test_editing_in_pending_approval_is_409(marco_api, complete_draft):
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    cur = marco_api.get(f"/api/requests/{d['reference']}").json()
    assert cur["status"] == "PENDING_APPROVAL"
    for url in ("draft", "steps/1"):
        r = marco_api.patch(
            f"/api/requests/{d['reference']}/{url}", {"version": cur["version"], "notes": "x"}, format="json"
        )
        assert r.status_code == 409 and r.json()["code"] == "not_editable" and r.json()["message"]


def test_rejected_and_returned_requests_can_be_revised_and_keep_their_status(marco_api, complete_draft):
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    for status in ("REJECTED", "RETURNED"):
        ShipmentRequest.objects.filter(reference=d["reference"]).update(status=status)
        cur = marco_api.get(f"/api/requests/{d['reference']}").json()
        r = marco_api.patch(
            f"/api/requests/{d['reference']}/draft",
            {"version": cur["version"], "notes": status},
            format="json",
        )
        assert r.status_code == 200 and r.json()["status"] == status


def test_stale_version_gets_409(marco_api, new_draft):
    d = new_draft()
    first = marco_api.patch(
        f"/api/requests/{d['reference']}/draft", {"version": d["version"], "notes": "tab 1"}, format="json"
    )
    assert first.status_code == 200 and first.json()["version"] != d["version"]
    stale = marco_api.patch(
        f"/api/requests/{d['reference']}/draft", {"version": d["version"], "notes": "tab 2"}, format="json"
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    assert ShipmentRequest.objects.get(reference=d["reference"]).notes == "tab 1"
    missing = marco_api.patch(f"/api/requests/{d['reference']}/draft", {"notes": "no version"}, format="json")
    assert missing.status_code == 400


# ------------------------------------------------------------------ discard / duplicate
def test_discard_cancels_a_never_submitted_draft(marco_api, new_draft):
    d = new_draft()
    r = marco_api.post(f"/api/requests/{d['reference']}/discard")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert RequestEvent.objects.filter(request__reference=d["reference"], action="Discarded").exists()
    assert ShipmentRequest.objects.filter(reference=d["reference"]).exists()  # kept and numbered
    assert marco_api.post(f"/api/requests/{d['reference']}/discard").status_code == 409  # already cancelled


def test_discard_is_refused_after_submit_and_for_revisions(marco_api, complete_draft):
    d = complete_draft()
    marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    assert marco_api.post(f"/api/requests/{d['reference']}/discard").status_code == 409
    ShipmentRequest.objects.filter(reference=d["reference"]).update(status="REJECTED")
    assert marco_api.post(f"/api/requests/{d['reference']}/discard").status_code == 409


def test_duplicate_copies_everything_but_the_ship_day(marco_api, complete_draft):
    d = complete_draft()
    r = marco_api.post(f"/api/requests/{d['reference']}/duplicate")
    assert r.status_code == 201
    copy = r.json()
    assert copy["reference"] != d["reference"] and copy["status"] == "DRAFT"
    assert copy["ship_day_requested"] is None and copy["consignee_company"] == "Ospedale Test"
    assert len(copy["lines"]) == 1 and copy["lines"][0]["pvari_code"] == "P9993"
    assert RequestEvent.objects.filter(
        request__reference=copy["reference"], action=f"Duplicated from {d['reference']}"
    ).exists()
    assert copy["duplicated_from"] == d["reference"]
    assert d["duplicated_from"] is None if "duplicated_from" in d else True
    rows = {x["reference"]: x for x in marco_api.get("/api/requests").json()["results"]}
    assert rows[copy["reference"]]["duplicated_from"] == d["reference"]
    assert rows[d["reference"]]["duplicated_from"] is None
    assert marco_api.get(f"/api/requests/{d['reference']}").json()["duplicated_from"] is None
