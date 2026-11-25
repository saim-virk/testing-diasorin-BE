"""Load the prototype's sample requests (`prototype_requests.json`, extracted from the HTML prototype's seed).

Dev / demo only. Idempotent: a reference that already exists is left alone. Times in the prototype are
Europe/Rome wall-clock; they are stored as UTC.
"""

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.accounts.models import User
from apps.masterdata.models import Carrier, PVARICode

from .enums import EventKind, RoundState, SkipReason, Status
from .models import ApprovalRound, RequestEvent, ShipmentRequest
from .services import derive, drafts

DATA = Path(__file__).with_name("prototype_requests.json")
ROME = ZoneInfo("Europe/Rome")

SCOPE = {"Italy": "ITALY", "EU": "EU", "Extra-EU": "EXTRA_EU", "USA": "USA"}
STATUS = {label: value for value, label in Status.choices}
ROLE = {
    "requester": "requester",
    "approver": "approver",
    "orderentry": "customer_management",
    "system": "system",
}
ROUND_STATE = {
    "Pending": RoundState.PENDING,
    "Approved": RoundState.APPROVED,
    "Rejected": RoundState.REJECTED,
    "Not required": RoundState.NOT_REQUIRED,
    "Skipped": RoundState.NOT_REQUIRED,
}
YESNO = {"Yes": "YES", "No": "NO"}
DECISIONS = {"approved", "rejected", "returned", "resubmitted"}


def _when(text: str | None):
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ROME)


def _text(value):
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def _skip_reason(comment: str) -> str | None:
    if "exception" in comment or "exempt" in comment:
        return SkipReason.REQUESTER_EXEMPT
    if "switched off for" in comment:
        return SkipReason.CENTRE_OFF
    if "switched off" in comment:
        return SkipReason.GLOBAL_OFF
    return None


def _parse_quantity(text: str):
    """ "12 pcs / lot L-77412" -> (12, "pcs", "L-77412")."""
    text = text or ""
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*([^/+]*)", text)
    qty = Decimal(m.group(1).replace(",", ".")) if m else None
    uom = _text(m.group(2)) if m else None
    lot = re.search(r"lot\s+(\S+)", text, re.I)
    return qty, uom, (lot.group(1) if lot else None)


def _load_lines(req: ShipmentRequest, items: list[dict]) -> None:
    rows = []
    for it in items:
        qty, uom, lot = _parse_quantity(it.get("qty", ""))
        pvari = PVARICode.objects.filter(code=it.get("code")).first() if it.get("code") else None
        rows.append(
            {
                "pvari_code": it.get("code") or None,
                "description": it.get("desc"),
                "quantity": qty,
                "uom": uom,
                "lot_number": lot,
                "net_weight_kg": Decimal(str(it["weight"])) if it.get("weight") not in (None, "") else None,
                "standard_price": Decimal(str(it["amount"])) if it.get("amount") not in (None, "") else None,
                "currency": it.get("currency"),
                "country_of_origin": it.get("origin"),
                "temperature": pvari.default_temperature if pvari else "AMBIENT",
            }
        )
    drafts._replace_lines(req, rows)


def _load_events(req: ShipmentRequest, src: dict) -> None:
    comments = {(c["at"], c["by"]): c for c in src.get("comments", [])}
    used = set()
    for h in src.get("history", []):
        c = comments.get((h["at"], h["by"]))
        decision = c is not None and c["kind"] in DECISIONS
        if decision:
            used.add((h["at"], h["by"]))
        user = User.objects.filter(email=h["by"]).first()
        RequestEvent.objects.create(
            request=req,
            at=_when(h["at"]),
            actor=user,
            actor_role=ROLE.get(h["role"], "system"),
            kind=EventKind.EVENT,
            in_conversation=decision or h["action"] in ("Submitted", "Returned for correction", "Rejected"),
            action=h["action"],
            to_status=STATUS.get(h["action"], ""),
            note=c["text"] if decision else h.get("note", ""),
        )
    for key, c in comments.items():
        if key in used:
            continue
        RequestEvent.objects.create(
            request=req,
            at=_when(c["at"]),
            actor=User.objects.filter(email=c["by"]).first(),
            actor_role=ROLE.get(c["role"], "system"),
            kind=EventKind.QUESTION if c["kind"] == "question" else EventKind.COMMENT,
            in_conversation=True,
            action=c["kind"].capitalize(),
            note=c["text"],
        )


def _load_approval(req: ShipmentRequest, src: dict) -> None:
    ap = src.get("approval")
    if not ap or not src["status"] or src["status"] == "Draft":
        return
    state = ROUND_STATE.get(ap["state"], RoundState.NOT_REQUIRED)
    rnd = ApprovalRound.objects.create(
        request=req,
        round_number=1,
        required=bool(ap["required"]),
        skip_reason=None if ap["required"] else _skip_reason(ap.get("comment", "")),
        cost_centre_code=src.get("cc") or "",
        state=state,
        decided_by=User.objects.filter(email=ap.get("decidedBy")).first() if ap.get("decidedBy") else None,
        decided_at=_when(ap.get("decidedAt")),
        started_at=_when(src["created"]),
    )
    rnd.eligible_approvers.set(User.objects.filter(email__in=ap.get("approvers", [])))


def _load_one(src: dict) -> ShipmentRequest | None:
    if ShipmentRequest.objects.filter(reference=src["id"]).exists():
        return None
    requester = User.objects.get(email=src["applicantEmail"])
    rc = src.get("rcpt") or {}
    created = _when(src["created"])
    status = STATUS[src["status"]]
    us = src.get("usa") or {}
    oe = src.get("oe") or {}
    req = ShipmentRequest(
        reference=src["id"],
        requester=requester,
        created_at=created,
        status=status,
        destination=SCOPE[src["scope"]],
        ships_from_code="SALUGGIA" if src["recCode"] != "DS-IT-GER" else "GERENZANO",
        ship_day_requested=date.fromisoformat(src["shipDay"]) if src.get("shipDay") else None,
        credit_note_pending="YES" if src.get("credit") == "Yes" else "NA",
        applicant_name=src["applicant"],
        applicant_email=src["applicantEmail"],
        applicant_department=_text(src.get("dept")),
        applicant_phone=_text(src.get("phone")),
        alt_contact_name=_text(src.get("altContact")),
        alt_contact_phone=_text(src.get("altPhone")),
        recipient_code=src.get("recCode"),
        reason_code=src.get("reason"),
        consignee_company=_text(rc.get("company")),
        consignee_first_name=_text(rc.get("first")),
        consignee_last_name=_text(rc.get("last")),
        consignee_department=_text(rc.get("dept")),
        consignee_street=_text(rc.get("street")),
        consignee_street2=_text(rc.get("street2")),
        consignee_postal_code=_text(rc.get("zip")),
        consignee_city=_text(rc.get("city")),
        consignee_province=_text(rc.get("prov")),
        consignee_country_code=_text(rc.get("country")),
        consignee_phone=_text(rc.get("phone")),
        consignee_email=_text(rc.get("email")),
        consignee_vat=_text(rc.get("vat")),
        po_number=_text(src.get("po")),
        cost_centre_code=src.get("cc"),
        material_type={"Other": "OTHER", "Raw materials": "RAW_MATERIALS"}.get(src.get("matType"), "IVD"),
        material_type_other=_text(src.get("otherType")),
        datalogger="YES",
        shipped_by_employee=_text(src.get("byEmp")),
        shipped_by_recipient=_text(src.get("byRec")),
        dedicated_transport=src.get("dedicated") == "Yes",
        dedicated_transport_note=_text(src.get("dedicatedNote")),
        notes=_text(src.get("notes")),
        us_usda_guideline=YESNO.get(us.get("usdaG")),
        us_usda_guideline_number=_text(us.get("usdaGNo")),
        us_usda_permit=YESNO.get(us.get("usdaP")),
        us_attach_000614=YESNO.get(us.get("att614")),
        us_cdc_permit=YESNO.get(us.get("cdc")),
        us_importer_certification_statement=YESNO.get(us.get("ics")),
        cm_owner=User.objects.filter(email=oe.get("owner")).first() if oe.get("owner") else None,
        carrier_name=_text(oe.get("carrier")),
        carrier=Carrier.objects.filter(name=oe.get("carrier")).first() if oe.get("carrier") else None,
        awb=_text(oe.get("awb")),
        verified_at=_when(oe.get("verifiedAt")),
        packed_at=_when(oe.get("packedAt")),
        shipped_at=_when(oe.get("shippedAt")),
        delivered_at=_when(oe.get("deliveredAt")),
    )
    if status != Status.DRAFT:
        req.submitted_at = req.last_submitted_at = created
        req.declaration_accepted_at = created
    drafts.resolve_refs(req)
    req.save()
    _load_lines(req, src.get("items", []))
    rows = [
        {
            "count": p.get("n"),
            "packaging_code": p.get("pack"),
            "dimensions": p.get("dims"),
            "gross_weight_kg": Decimal(str(p["gross"])) if p.get("gross") else None,
        }
        for p in src.get("parcels", [])
    ]
    drafts._replace_parcels(req, rows)
    lines = list(req.lines.all())
    req.dangerous_features = derive.derived_hazard(lines) or "UNINFECTED"
    req.overall_temperature = derive.overall_temperature(lines)
    req.save()
    _load_approval(req, src)
    _load_events(req, src)
    return req


@transaction.atomic
def load_prototype_requests() -> int:
    """Create the sample requests that do not exist yet; returns how many were created."""
    sources = json.loads(DATA.read_text(encoding="utf-8"))
    created = [r for src in sources if (r := _load_one(src)) is not None]
    # keep the counter ahead of the loaded numbers so new requests continue the sequence
    from .models import ReferenceCounter

    for src in sources:
        year, number = (int(p) for p in src["id"].split("-")[1:])
        counter, _ = ReferenceCounter.objects.get_or_create(year=year)
        if counter.last_number < number:
            counter.last_number = number
            counter.save(update_fields=["last_number"])
    return len(created)
