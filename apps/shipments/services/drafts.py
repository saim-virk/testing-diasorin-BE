"""Create, save (Continue / Save draft), discard and duplicate requests.

Continue  = apply step n, validate step n only, save (nothing is saved when it fails).
Save draft = apply anything, no validation.
Both: owner only, Draft / Rejected / Returned only, and the `version` the client read must still be current.
"""

from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.accounts.enums import AppRole
from apps.masterdata.enums import Destination, destination_for_scope_group
from apps.masterdata.models import (
    Branch,
    CostCentre,
    Country,
    PackagingType,
    PVARICode,
    ReasonCode,
    ShipsFromSite,
)

from ..enums import EventKind, Status
from ..models import Parcel, RequestEvent, RequestLine, ShipmentRequest
from . import access, derive
from .errors import StaleVersion, StepValidationError, TransitionError
from .reference import next_reference
from .validation import today_rome, validate_step

EDITABLE_STATUSES = (Status.DRAFT, Status.REJECTED, Status.RETURNED)

STEP_FIELDS = {
    1: [
        "destination",
        "applicant_name",
        "applicant_department",
        "applicant_phone",
        "alt_contact_name",
        "alt_contact_phone",
        "ships_from_code",
        "ship_day_requested",
        "credit_note_pending",
    ],
    2: [
        "recipient_code",
        "reason_code",
        "consignee_company",
        "consignee_first_name",
        "consignee_last_name",
        "consignee_department",
        "consignee_street",
        "consignee_street2",
        "consignee_postal_code",
        "consignee_city",
        "consignee_province",
        "consignee_country_code",
        "consignee_phone",
        "consignee_email",
        "consignee_vat",
        "po_number",
        "cost_centre_code",
    ],
    3: [
        "lines",
        "dangerous_features",
        "other_hazard_text",
        "material_type",
        "material_type_other",
        "rm_description",
        "rm_kind",
        "rm_protein",
        "rm_lot_number",
        "rm_quantity",
        "rm_number_of_vials",
        "rm_leftover_stock",
        "rm_article_number",
        "rm_date_of_shipment",
    ],
    4: [
        "datalogger",
        "shipped_by_employee",
        "shipped_by_recipient",
        "parcels",
        "dedicated_transport",
        "dedicated_transport_note",
        "us_usda_guideline",
        "us_usda_guideline_number",
        "us_usda_permit",
        "us_attach_000614",
        "us_cdc_permit",
        "us_importer_certification_statement",
        "notes",
    ],
}
ALL_FIELDS = [f for n in sorted(STEP_FIELDS) for f in STEP_FIELDS[n]]
LINE_FIELDS = [
    "pvari_code",
    "description",
    "quantity",
    "uom",
    "lot_number",
    "net_weight_kg",
    "standard_price",
    "currency",
    "country_of_origin",
    "temperature",
]
PARCEL_FIELDS = ["count", "packaging_code", "dimensions", "gross_weight_kg"]
# columns that only exist on PVARI lines (free-text lines show "N.A.")
PVARI_ONLY = ["net_weight_kg", "standard_price", "currency", "country_of_origin"]


def _clean(value):
    """Blank text is no value."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def version_of(req: ShipmentRequest) -> str:
    return req.updated_at.isoformat()


def check_version(req: ShipmentRequest, version: str | None) -> None:
    sent = parse_datetime(version) if isinstance(version, str) else None
    if sent is None:
        raise StepValidationError(0, {"version": ["Send the version you read."]})
    if sent != req.updated_at:
        raise StaleVersion()


def record_event(
    req,
    actor,
    action,
    *,
    from_status="",
    to_status="",
    note="",
    in_conversation=False,
    kind=EventKind.EVENT,
    role=None,
):
    return RequestEvent.objects.create(
        request=req,
        actor=actor,
        actor_role=(role or AppRole.REQUESTER.value) if actor else "system",
        kind=kind,
        in_conversation=in_conversation,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=note,
    )


# ------------------------------------------------------------------ access
def can_view(user, req: ShipmentRequest) -> bool:
    """The owner sees everything; nobody else sees a request that was never submitted (see access.py)."""
    return access.can_view(user, req)


def require_owner(user, req: ShipmentRequest) -> None:
    if req.requester_id != user.pk:
        raise PermissionDenied("Only the person who made the request can change it.")


def require_editable(req: ShipmentRequest) -> None:
    if req.status not in EDITABLE_STATUSES:
        raise TransitionError(
            f"A request in status {Status(req.status).label} can no longer be edited.", "not_editable"
        )


# ------------------------------------------------------------------ resolving codes and snapshots
def resolve_refs(req: ShipmentRequest) -> None:
    """Point each coded field at its master row (and snapshot its label); an unknown code keeps the typed
    text with no row, which validation then reports."""
    site = ShipsFromSite.objects.filter(code=req.ships_from_code, is_active=True).first()
    req.ships_from = site

    branch = (
        Branch.objects.filter(code=req.recipient_code, is_active=True).first() if req.recipient_code else None
    )
    req.recipient_branch = branch
    req.recipient_branch_name = branch.name if branch else None

    reason = None
    if req.reason_code and req.destination in Destination.values:
        reason = ReasonCode.objects.filter(
            scope_group=destination_for_scope_group(req.destination), code=req.reason_code, is_active=True
        ).first()
    req.reason_ref = reason
    req.reason_label_it = reason.description_it if reason else None
    req.reason_label_en = reason.description_en if reason else None

    country = (
        Country.objects.filter(iso2=req.consignee_country_code, is_active=True).first()
        if req.consignee_country_code
        else None
    )
    req.consignee_country = country
    req.consignee_country_name = country.name if country else None

    centre = (
        CostCentre.objects.filter(code=req.cost_centre_code, is_active=True).first()
        if req.cost_centre_code
        else None
    )
    req.cost_centre_ref = centre
    req.cost_centre_name = centre.name if centre else None


def _snapshot_line(ln: RequestLine) -> None:
    pvari = PVARICode.objects.filter(code=ln.pvari_code, is_active=True).first() if ln.pvari_code else None
    ln.pvari_ref = pvari
    ln.un_number = (pvari.un_number or None) if pvari else None
    ln.hazard = pvari.hazard if pvari else None
    if not ln.pvari_code:  # free-text line: the PVARI-only columns are N.A.
        for f in PVARI_ONLY:
            setattr(ln, f, None)


def _replace_lines(req: ShipmentRequest, rows: list[dict]) -> None:
    req.lines.all().delete()
    for i, row in enumerate(rows):
        ln = RequestLine(request=req, position=i, **{f: _clean(row.get(f)) for f in LINE_FIELDS})
        _snapshot_line(ln)
        ln.save()


def _replace_parcels(req: ShipmentRequest, rows: list[dict]) -> None:
    req.parcels.all().delete()
    for i, row in enumerate(rows):
        p = Parcel(request=req, position=i, **{f: _clean(row.get(f)) for f in PARCEL_FIELDS})
        pack = (
            PackagingType.objects.filter(code=p.packaging_code, is_active=True).first()
            if p.packaging_code
            else None
        )
        p.packaging_ref = pack
        if pack and not p.dimensions:
            p.dimensions = pack.dimensions or None
        p.save()


def refresh_line_snapshots(req: ShipmentRequest) -> None:
    for ln in req.lines.all():
        _snapshot_line(ln)
        ln.save()


def update_derived(req: ShipmentRequest, *, lock: bool) -> None:
    """Recompute the cached overall temperature; keep dangerous features consistent with the lines."""
    lines = list(req.lines.all())
    req.overall_temperature = derive.overall_temperature(lines)
    hazard = derive.derived_hazard(lines)
    if hazard is None:
        return
    if req.dangerous_features is None:
        req.dangerous_features = hazard
    elif lock and req.dangerous_features not in derive.allowed_dangerous_features(lines):
        req.dangerous_features = hazard


# ------------------------------------------------------------------ create / save
def _apply(req: ShipmentRequest, data: dict) -> None:
    for name, value in data.items():
        if name == "lines":
            _replace_lines(req, value)
        elif name == "parcels":
            _replace_parcels(req, value)
        else:
            setattr(req, name, _clean(value) if name != "dedicated_transport" else bool(value))
    if req.credit_note_pending is None:
        req.credit_note_pending = "NA"


@transaction.atomic
def create_draft(user, data: dict | None = None, *, step: int | None = None) -> ShipmentRequest:
    """First save. With `step`, that step is validated first (Continue); nothing is created if it fails."""
    data = data or {}
    rows = {k: data[k] for k in ("lines", "parcels") if k in data}
    data = {k: v for k, v in data.items() if k not in rows}
    req = ShipmentRequest(
        reference=next_reference(today_rome().year),
        requester=user,
        applicant_email=user.email,
        applicant_name=" ".join(p for p in (user.first_name, user.last_name) if p) or None,
        applicant_department=user.department or None,
        applicant_phone=user.phone or None,
        cost_centre_code=user.default_cost_centre.code if user.default_cost_centre_id else None,
    )
    _apply(req, data)
    resolve_refs(req)
    req.save()  # rows need a saved parent
    _apply(req, rows)
    if "lines" in rows:
        update_derived(req, lock=step is None)
        req.save()
    if step:
        errors = validate_step(req, step)
        if errors:
            raise StepValidationError(step, errors)
    record_event(req, user, "Draft created", to_status=Status.DRAFT)
    return req


@transaction.atomic
def save(req_id: int, user, data: dict, version: str | None, *, step: int | None = None) -> ShipmentRequest:
    """Continue (`step` given: that step is validated, nothing is saved on errors) or Save draft (no validation)."""
    req = ShipmentRequest.objects.select_for_update().get(pk=req_id)
    require_owner(user, req)
    require_editable(req)
    check_version(req, version)
    if step:
        extra = set(data) - set(STEP_FIELDS[step])
        if extra:
            raise StepValidationError(
                step, {f: ["This field does not belong to this step."] for f in sorted(extra)}
            )
    _apply(req, data)
    resolve_refs(req)
    req.save()
    if "lines" in data or step == 3:
        update_derived(req, lock=step is None)
        req.save()
    if step:
        errors = validate_step(req, step)
        if errors:
            raise StepValidationError(step, errors)  # rolls the whole save back
    req.refresh_from_db()
    return req


# ------------------------------------------------------------------ discard / duplicate
@transaction.atomic
def discard(req_id: int, user) -> ShipmentRequest:
    """A draft that was never submitted is cancelled (kept, numbered); anything else is refused."""
    req = ShipmentRequest.objects.select_for_update().get(pk=req_id)
    require_owner(user, req)
    if req.status != Status.DRAFT or req.submitted_at is not None:
        raise TransitionError("Only a draft that was never submitted can be discarded.", "not_discardable")
    old = req.status
    req.status = Status.CANCELLED
    req.save(update_fields=["status", "updated_at"])
    record_event(req, user, "Discarded", from_status=old, to_status=Status.CANCELLED)
    return req


COPIED_FIELDS = [
    f for f in ALL_FIELDS if f not in ("lines", "parcels", "ship_day_requested")
]  # the ship day is never copied; attachments and the declaration are not either


@transaction.atomic
def duplicate(source_id: int, user) -> ShipmentRequest:
    src = ShipmentRequest.objects.get(pk=source_id)
    if not can_view(user, src):
        raise NotFound("Not found.")
    if src.requester_id != user.pk:  # a copy would carry the owner's identity: own requests only
        raise PermissionDenied("Only the person who made the request can duplicate it.")
    req = ShipmentRequest(
        reference=next_reference(today_rome().year),
        requester=user,
        applicant_email=user.email,
        duplicated_from=src,
    )
    for f in COPIED_FIELDS:
        setattr(req, f, getattr(src, f))
    req.ship_day_requested = None
    resolve_refs(req)
    req.save()
    for ln in src.lines.all():
        ln.pk, ln.request = None, req
        ln.save()
    for p in src.parcels.all():
        p.pk, p.request, p.confirmed_at, p.confirmed_by = None, req, None, None
        p.save()
    update_derived(req, lock=False)
    req.save()
    record_event(req, user, f"Duplicated from {src.reference}", to_status=Status.DRAFT)
    return req
