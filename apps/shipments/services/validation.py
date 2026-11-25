"""Server-side validation, one function per step (REQUIREMENTS section 3). Submit runs all of them.

Every function reads the *saved* request (codes are resolved against the master data at call time, so a
rule or master-data change since the step was saved is caught at submit) and returns field errors.
"""

import re
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone

from apps.masterdata.enums import Destination, destination_for_scope_group
from apps.masterdata.models import (
    Branch,
    CostCentre,
    Country,
    PVARICode,
    ReasonCode,
    ShipsFromSite,
)
from apps.platform_config.models import SiteConfig

from ..enums import AttachmentKind, DangerousFeatures, MaterialType, YesNo
from . import derive
from .errors import StepValidationError

REQUIRED = "This field is required."
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
OTHER_UNIT = "other"  # the form's "Other" choice; the typed unit is stored instead
PHONE_RE = re.compile(r"^[0-9\s+\-()]+$")


def today_rome() -> date:
    return timezone.now().astimezone(ZoneInfo(getattr(settings, "TIME_ZONE_DISPLAY", "Europe/Rome"))).date()


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _req(errors: dict, req, field: str, message: str = REQUIRED) -> bool:
    """Record a required-field error; True if the value is present."""
    if _blank(getattr(req, field)):
        errors.setdefault(field, []).append(message)
        return False
    return True


def phone_error(value: str) -> str | None:
    """Loose check: digits, spaces and + - ( ) only, at least 6 digits."""
    if not PHONE_RE.match(value) or sum(ch.isdigit() for ch in value) < 6:
        return "Enter a valid phone number (digits, spaces, + - ( ), at least 6 digits)."
    return None


def saluggia_hint(site: ShipsFromSite) -> str:
    days = ", ".join(WEEKDAYS[d] for d in sorted(site.allowed_weekdays or []))
    return f"{site.name} ships {days}."


# ---------------------------------------------------------------- step 1
def validate_step1(req) -> dict:
    e: dict = {}
    if _blank(req.destination):
        e["destination"] = ["Choose where the shipment is going."]
    elif req.destination not in Destination.values:
        e["destination"] = ["Choose a valid destination."]
    _req(e, req, "applicant_name", "Applicant is mandatory.")
    if _req(e, req, "applicant_phone", "A contact phone is mandatory."):
        if msg := phone_error(req.applicant_phone):
            e["applicant_phone"] = [msg]
    if not _blank(req.alt_contact_phone) and (msg := phone_error(req.alt_contact_phone)):
        e["alt_contact_phone"] = [msg]

    site = None
    if _req(e, req, "ships_from_code", "Choose where the shipment leaves from."):
        site = ShipsFromSite.objects.filter(code=req.ships_from_code, is_active=True).first()
        if site is None:
            e["ships_from_code"] = ["Choose a ships-from warehouse from the list."]
    if _req(e, req, "ship_day_requested", "Requested shipping day is mandatory."):
        day = req.ship_day_requested
        if day < today_rome():
            e["ship_day_requested"] = ["The shipping day cannot be in the past."]
        elif site is not None and not site.allows_ship_day(day):  # read from the DB row, never cached
            e["ship_day_requested"] = [
                f"{WEEKDAYS[day.weekday()]} is not a shipping day. {saluggia_hint(site)}"
            ]
    if req.credit_note_pending not in ("YES", "NA"):
        e["credit_note_pending"] = ["Say whether the goods are pending a credit note."]
    return e


# ---------------------------------------------------------------- step 2
def find_branch(req) -> Branch | None:
    return (
        Branch.objects.filter(code=req.recipient_code, is_active=True).first() if req.recipient_code else None
    )


def po_required(req, branch: Branch | None = None) -> bool:
    """PO is mandatory when the Admin rule is on and the chosen branch is flagged (DS Inc, SOP 15.0016)."""
    branch = branch or find_branch(req)
    return bool(branch and branch.po_required and SiteConfig.load().po_mandatory_us)


def validate_step2(req) -> dict:
    e: dict = {}
    dest = req.destination if req.destination in Destination.values else None

    if _req(e, req, "recipient_code", "Recipient code is mandatory."):
        branch = find_branch(req)
        if branch is None:
            e["recipient_code"] = ["Pick a recipient code from the list."]
        elif dest and branch.scope != dest:
            e["recipient_code"] = ["This recipient code does not belong to the selected destination."]
    branch = find_branch(req)

    if _req(e, req, "reason_code", "Reason code is mandatory."):
        group = destination_for_scope_group(dest) if dest else None
        ok = (
            bool(group)
            and ReasonCode.objects.filter(scope_group=group, code=req.reason_code, is_active=True).exists()
        )
        if not ok:
            e["reason_code"] = ["This reason code is not valid for the selected destination."]

    for field, msg in [
        ("consignee_company", "Company / institution is mandatory."),
        ("consignee_first_name", "Contact first name is mandatory."),
        ("consignee_last_name", "Surname is mandatory."),
        ("consignee_street", "Street and number are mandatory."),
        ("consignee_postal_code", "Postal code is mandatory."),
        ("consignee_city", "City is mandatory."),
    ]:
        _req(e, req, field, msg)
    if _req(e, req, "consignee_phone", "A recipient phone number is mandatory — the carrier needs it."):
        if msg := phone_error(req.consignee_phone):
            e["consignee_phone"] = [msg]
    if not _blank(req.consignee_email):
        try:
            validate_email(req.consignee_email)
        except DjangoValidationError:
            e["consignee_email"] = ["That does not look like an email address."]

    if _req(e, req, "consignee_country_code", "Country is mandatory."):
        country = Country.objects.filter(iso2=req.consignee_country_code, is_active=True).first()
        if country is None or (dest and country.scope != dest):
            e["consignee_country_code"] = ["This country is not valid for the selected destination."]
        elif dest == Destination.ITALY and country.iso2 != "IT":
            e["consignee_country_code"] = ["The country is fixed to Italy for Italian destinations."]
        elif dest == Destination.USA and country.iso2 != "US":
            e["consignee_country_code"] = ["The country is fixed to United States for USA destinations."]

    if po_required(req, branch):
        _req(e, req, "po_number", "PO number is mandatory for DS Inc. shipments (SOP 15.0016).")

    if _req(e, req, "cost_centre_code", "Cost centre to be charged is mandatory."):
        if not CostCentre.objects.filter(code=req.cost_centre_code, is_active=True).exists():
            e["cost_centre_code"] = ["Pick an active cost centre from the list."]
    return e


# ---------------------------------------------------------------- step 3
def _line_errors(ln) -> dict:
    e: dict = {}
    if (
        not _blank(ln.pvari_code)
        and not PVARICode.objects.filter(code=ln.pvari_code, is_active=True).exists()
    ):
        e["pvari_code"] = ["Pick a PVARI code from the list."]
    for field, msg in [
        ("description", "Description is mandatory."),
        ("quantity", "Quantity is mandatory."),
        ("uom", "Choose a unit."),
        ("temperature", "Choose the transport temperature for this line."),
    ]:
        if _blank(getattr(ln, field)):
            e[field] = [msg]
    if ln.quantity is not None and ln.quantity <= 0:
        e["quantity"] = ["Enter a number greater than 0."]
    if ln.uom == OTHER_UNIT:  # "Other" chosen but the unit never typed
        e["uom"] = ["Choose a unit."]
    if not _blank(ln.pvari_code):  # PVARI line: the extra columns are mandatory
        for field, msg in [
            ("lot_number", "Lot / batch is mandatory for PVARI lines."),
            ("net_weight_kg", "Net weight is mandatory for PVARI lines."),
            ("standard_price", "Standard price is mandatory for PVARI lines."),
            ("currency", "Currency is mandatory for PVARI lines."),
            ("country_of_origin", "Country of origin is mandatory for PVARI lines."),
        ]:
            if _blank(getattr(ln, field)):
                e[field] = [msg]
        if ln.net_weight_kg is not None and ln.net_weight_kg <= 0:
            e["net_weight_kg"] = ["Net weight must be greater than zero."]
        if ln.standard_price is not None and ln.standard_price < 0:
            e["standard_price"] = ["Standard price cannot be negative."]
    return e


def validate_step3(req) -> dict:
    e: dict = {}
    cfg = SiteConfig.load()
    lines = list(req.lines.all())
    if not lines:
        e["lines"] = {"non_field_errors": ["Add at least one line."]}
    else:
        per_line = {i: err for i, ln in enumerate(lines) if (err := _line_errors(ln))}
        if per_line:
            e["lines"] = per_line

    if _blank(req.dangerous_features):
        e["dangerous_features"] = ["Choose the dangerous features of the material."]
    elif req.dangerous_features not in derive.allowed_dangerous_features(lines):
        locked = derive.derived_hazard(lines)
        e["dangerous_features"] = [
            "The lines contain infectious material, so this must be Infectious."
            if locked == DangerousFeatures.INFECTIOUS
            else "This choice does not match the PVARI codes on the lines."
        ]
    if req.dangerous_features == DangerousFeatures.OTHER:
        _req(e, req, "other_hazard_text", "Describe the other hazard (from the MSDS).")
        if cfg.msds_required_other_hazard and not req.attachments.filter(kind=AttachmentKind.MSDS).exists():
            e["attachments"] = ["Attach the Material Safety Data Sheet (MSDS)."]

    if _blank(req.material_type):
        e["material_type"] = ["Select the material type."]
    elif req.material_type == MaterialType.OTHER:
        _req(e, req, "material_type_other", "Specify the material type.")
    return e


# ---------------------------------------------------------------- step 4
def validate_step4(req) -> dict:
    e: dict = {}
    cfg = SiteConfig.load()
    if _blank(req.datalogger):
        e["datalogger"] = ["The datalogger choice is mandatory."]
    if req.dedicated_transport:
        _req(e, req, "dedicated_transport_note", "Say which dedicated transport supplier is needed.")

    parcels = list(req.parcels.all())
    if len(parcels) > cfg.max_parcel_lines:
        e["parcels"] = {"non_field_errors": [f"At most {cfg.max_parcel_lines} parcel lines are allowed."]}
    else:
        per = {}
        for i, p in enumerate(parcels):
            pe = {}
            if p.count is not None and p.count < 1:
                pe["count"] = ["Number of parcels must be at least 1."]
            if p.gross_weight_kg is not None and p.gross_weight_kg < Decimal(0):
                pe["gross_weight_kg"] = ["Gross weight cannot be negative."]
            if pe:
                per[i] = pe
        if per:
            e["parcels"] = per

    if req.destination == Destination.USA:
        for field in (
            "us_usda_guideline",
            "us_usda_permit",
            "us_attach_000614",
            "us_cdc_permit",
            "us_importer_certification_statement",
        ):
            if getattr(req, field) not in YesNo.values:
                e[field] = ["Answer Yes or No (DSI-SOP-000354)."]
        if req.us_usda_guideline == YesNo.YES:
            _req(e, req, "us_usda_guideline_number", "The USDA guideline number is mandatory.")
    return e


VALIDATORS = {1: validate_step1, 2: validate_step2, 3: validate_step3, 4: validate_step4}


def validate_step(req, step: int) -> dict:
    """Field errors of step `step` only."""
    return VALIDATORS[step](req)


def ensure_step(req, step: int) -> None:
    if errors := validate_step(req, step):
        raise StepValidationError(step, errors)


def validate_all(req, declaration: bool = True) -> None:
    """Submit: every step plus the declaration. Raises for the first failing step (`failed_steps` lists all)."""
    found = {n: errs for n, fn in VALIDATORS.items() if (errs := fn(req))}
    if not declaration:
        found[5] = {"declaration": ["Confirm the declaration to submit."]}
    if found:
        first = min(found)
        raise StepValidationError(first, found[first], failed_steps=sorted(found))
