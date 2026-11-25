from datetime import timedelta

import pytest

from apps.masterdata.models import Branch, CostCentre, CostCentreApprover, Country, ReasonCode
from apps.shipments.services.validation import today_rome

RECIPIENT = {
    "consignee_company": "Ospedale Test",
    "consignee_first_name": "Anna",
    "consignee_last_name": "Verdi",
    "consignee_street": "Via Roma 1",
    "consignee_postal_code": "10100",
    "consignee_city": "Torino",
    "consignee_phone": "+39 011 123456",
}


def day_on(weekday: int):
    """The next date (from tomorrow on) that falls on `weekday` (0 = Monday)."""
    d = today_rome() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def world(db, make_user):
    """Branches, a cost centre with an approver, and the requester Marco (+ approver Giulia)."""
    it = Country.objects.get(iso2="IT")
    de = Country.objects.get(iso2="DE")
    us = Country.objects.get(iso2="US")
    Branch.objects.create(code="DS-IT-SAL", name="Diasorin Italia — Saluggia", scope="ITALY", country=it)
    Branch.objects.create(code="DS-DE-DIE", name="Diasorin Deutschland", scope="EU", country=de)
    Branch.objects.create(
        code="DS-US-STW", name="Diasorin Inc. — Stillwater", scope="USA", country=us, po_required=True
    )
    Branch.objects.create(code="DS-US-AUS", name="Diasorin Molecular LLC", scope="USA", country=us)
    giulia = make_user("g.ferrari@diasorin.com", first_name="Giulia", last_name="Ferrari")
    cc = CostCentre.objects.create(code="CC-4410", name="Warehouse", approval_required=True)
    CostCentreApprover.objects.create(cost_centre=cc, user=giulia)
    marco = make_user(
        "m.rossi@diasorin.com",
        first_name="Marco",
        last_name="Rossi",
        phone="+39 335 118 4402",
        department="Warehouse",
        default_cost_centre=cc,
    )
    return {"marco": marco, "giulia": giulia, "cc": cc}


@pytest.fixture
def reason_it():
    return ReasonCode.objects.filter(scope_group="ITALY").first().code


@pytest.fixture
def reason_eu():
    return ReasonCode.objects.filter(scope_group="EU_EXTRA").first().code


@pytest.fixture
def marco_api(world, api, sign_in):
    sign_in("m.rossi@diasorin.com")
    return api


@pytest.fixture
def payloads(reason_it, reason_eu):
    """Valid step payloads for an Italian request (Saluggia on a Monday) and helpers for USA / EU."""

    def step1(**kw):
        d = {
            "destination": "ITALY",
            "applicant_name": "Marco Rossi",
            "applicant_phone": "+39 335 118 4402",
            "ships_from_code": "SALUGGIA",
            "ship_day_requested": day_on(0).isoformat(),
            "credit_note_pending": "NA",
        }
        return {**d, **kw}

    def step2(**kw):
        d = {
            "recipient_code": "DS-IT-SAL",
            "reason_code": reason_it,
            "consignee_country_code": "IT",
            "cost_centre_code": "CC-4410",
            **RECIPIENT,
        }
        return {**d, **kw}

    def line(**kw):
        d = {
            "pvari_code": "P9993",
            "description": "Diagnostic products",
            "quantity": "4",
            "uom": "vial",
            "lot_number": "L1",
            "temperature": "COOL_2_8",
            "net_weight_kg": "1.2",
            "standard_price": "100",
            "currency": "EUR",
            "country_of_origin": "Italy",
        }
        return {**d, **kw}

    def step3(**kw):
        return {"lines": [line()], "dangerous_features": "UNINFECTED", "material_type": "IVD", **kw}

    def step4(**kw):
        return {"datalogger": "NO", "dedicated_transport": False, **kw}

    class P:
        pass

    p = P()
    p.step1, p.step2, p.step3, p.step4, p.line = step1, step2, step3, step4, line
    p.reason_eu, p.reason_it = reason_eu, reason_it
    return p


@pytest.fixture
def new_draft(marco_api):
    """POST an (optionally pre-filled) draft; returns the detail JSON."""

    def _new(**data):
        r = marco_api.post("/api/requests", data, format="json")
        assert r.status_code == 201, r.content
        return r.json()

    return _new


@pytest.fixture
def save_step(marco_api):
    def _save(ref, n, version, data, expect=200):
        r = marco_api.patch(f"/api/requests/{ref}/steps/{n}", {**data, "version": version}, format="json")
        assert r.status_code == expect, r.content
        return r.json()

    return _save


@pytest.fixture
def complete_draft(marco_api, new_draft, payloads):
    """A draft holding valid data for all four steps (saved with Save draft), ready to submit."""

    def _complete(**over):
        d = new_draft()
        body = {**payloads.step1(), **payloads.step2(), **payloads.step3(), **payloads.step4(), **over}
        r = marco_api.patch(
            f"/api/requests/{d['reference']}/draft", {**body, "version": d["version"]}, format="json"
        )
        assert r.status_code == 200, r.content
        return r.json()

    return _complete
