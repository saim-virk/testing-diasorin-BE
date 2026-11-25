import uuid
from pathlib import PurePath

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.masterdata.enums import Currency, Destination, Hazard, Temperature

from .enums import (
    ACTOR_ROLE_CHOICES,
    SYSTEM_ACTOR,
    AttachmentKind,
    CreditNote,
    DangerousFeatures,
    EventKind,
    MaterialType,
    RawMaterialKind,
    RoundState,
    SkipReason,
    Status,
    YesNo,
)

USER = settings.AUTH_USER_MODEL


class ReferenceCounter(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.year}: {self.last_number}"


def _s(max_length, **kw):
    """Nullable-for-drafts CharField (D12)."""
    return models.CharField(max_length=max_length, null=True, blank=True, **kw)


class ShipmentRequest(models.Model):
    # Identity
    reference = models.CharField(max_length=16, unique=True)
    requester = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="requests")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    duplicated_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )

    # Step 1
    destination = models.CharField(max_length=10, choices=Destination.choices, null=True, blank=True)
    ships_from_code = _s(20)
    ships_from = models.ForeignKey(
        "masterdata.ShipsFromSite", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ship_day_requested = models.DateField(null=True, blank=True)
    credit_note_pending = models.CharField(max_length=3, choices=CreditNote.choices, default=CreditNote.NA)

    # Applicant
    applicant_name = _s(200)
    applicant_email = models.EmailField()
    applicant_department = _s(150)
    applicant_phone = _s(40)
    alt_contact_name = _s(200)
    alt_contact_phone = _s(40)

    # Recipient
    recipient_code = _s(40)
    recipient_branch_name = _s(200)  # snapshot: survives a branch rename
    recipient_branch = models.ForeignKey(
        "masterdata.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason_code = _s(10)
    reason_label_it = _s(255)  # snapshots: the print view uses the reason code's print language
    reason_label_en = _s(255)
    reason_ref = models.ForeignKey(
        "masterdata.ReasonCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    consignee_company = _s(200)
    consignee_first_name = _s(100)
    consignee_last_name = _s(100)
    consignee_department = _s(150)
    consignee_street = _s(200)
    consignee_street2 = _s(200)
    consignee_postal_code = _s(20)
    consignee_city = _s(100)
    consignee_province = _s(100)
    consignee_country_code = _s(60)
    consignee_country_name = _s(100)
    consignee_country = models.ForeignKey(
        "masterdata.Country", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    consignee_phone = _s(40)
    consignee_email = _s(254)
    consignee_vat = _s(60)

    # Accounting
    po_number = _s(60)
    cost_centre_code = _s(20)
    cost_centre_name = _s(200)
    cost_centre_ref = models.ForeignKey(
        "masterdata.CostCentre", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Materials meta
    dangerous_features = models.CharField(
        max_length=12, choices=DangerousFeatures.choices, null=True, blank=True
    )
    other_hazard_text = _s(255)
    material_type = models.CharField(max_length=14, choices=MaterialType.choices, null=True, blank=True)
    material_type_other = _s(200)

    # Transport
    datalogger = models.CharField(max_length=3, choices=YesNo.choices, null=True, blank=True)
    shipped_by_employee = _s(200)
    shipped_by_recipient = _s(200)
    dedicated_transport = models.BooleanField(default=False)
    dedicated_transport_note = _s(255)

    # Raw-material details (only when material_type is RAW_MATERIALS)
    rm_description = _s(255)
    rm_kind = models.CharField(max_length=14, choices=RawMaterialKind.choices, null=True, blank=True)
    rm_protein = _s(100)
    rm_lot_number = _s(60)
    rm_quantity = _s(60)
    rm_number_of_vials = models.PositiveIntegerField(null=True, blank=True)
    rm_leftover_stock = _s(100)
    rm_article_number = _s(60)
    rm_date_of_shipment = models.DateField(null=True, blank=True)

    # US requirements (only when destination is USA)
    us_usda_guideline = models.CharField(max_length=3, choices=YesNo.choices, null=True, blank=True)
    us_usda_guideline_number = _s(60)
    us_usda_permit = models.CharField(max_length=3, choices=YesNo.choices, null=True, blank=True)
    us_attach_000614 = models.CharField(max_length=3, choices=YesNo.choices, null=True, blank=True)
    us_cdc_permit = models.CharField(max_length=3, choices=YesNo.choices, null=True, blank=True)
    us_importer_certification_statement = models.CharField(
        max_length=3, choices=YesNo.choices, null=True, blank=True
    )

    notes = models.TextField(null=True, blank=True)
    declaration_accepted_at = models.DateTimeField(null=True, blank=True)

    # Customer-management fulfilment
    cm_owner = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="claimed_requests"
    )
    carrier_name = _s(100)
    carrier = models.ForeignKey(
        "masterdata.Carrier", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    awb = _s(80)
    verified_at = models.DateTimeField(null=True, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    pod_note = _s(255)

    # Derived (cached; recomputed by the service layer)
    overall_temperature = models.CharField(max_length=10, choices=Temperature.choices, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["requester", "status"], name="req_requester_status_idx"),
            models.Index(fields=["status", "last_submitted_at"], name="req_status_submitted_idx"),
        ]

    def __str__(self):
        return self.reference


class RequestLine(models.Model):
    request = models.ForeignKey(ShipmentRequest, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    pvari_code = _s(10)
    pvari_ref = models.ForeignKey(
        "masterdata.PVARICode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    description = _s(255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    uom = _s(20)
    lot_number = _s(60)
    net_weight_kg = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    standard_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, null=True, blank=True)
    country_of_origin = _s(80)
    temperature = models.CharField(max_length=10, choices=Temperature.choices, null=True, blank=True)
    un_number = _s(10)
    hazard = models.CharField(max_length=12, choices=Hazard.choices, null=True, blank=True)

    class Meta:
        ordering = ["request", "position"]

    def __str__(self):
        return f"{self.request.reference} line {self.position}"


class Parcel(models.Model):
    request = models.ForeignKey(ShipmentRequest, on_delete=models.CASCADE, related_name="parcels")
    position = models.PositiveSmallIntegerField(default=0)
    count = models.PositiveSmallIntegerField(null=True, blank=True)
    packaging_code = _s(20)
    packaging_ref = models.ForeignKey(
        "masterdata.PackagingType", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dimensions = _s(60)
    gross_weight_kg = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["request", "position"]

    def __str__(self):
        return f"{self.request.reference} parcel {self.position}"


def attachment_path(instance, filename):
    """attachments/<reference>/<uuid4><extension>; the original name lives in `original_name`."""
    return f"attachments/{instance.request.reference}/{uuid.uuid4()}{PurePath(filename).suffix.lower()}"


class Attachment(models.Model):
    request = models.ForeignKey(ShipmentRequest, on_delete=models.CASCADE, related_name="attachments")
    kind = models.CharField(max_length=5, choices=AttachmentKind.choices, default=AttachmentKind.OTHER)
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.kind}: {self.original_name}"


class ApprovalRound(models.Model):
    request = models.ForeignKey(ShipmentRequest, on_delete=models.CASCADE, related_name="approval_rounds")
    round_number = models.PositiveSmallIntegerField()
    required = models.BooleanField(default=True)
    skip_reason = models.CharField(max_length=20, choices=SkipReason.choices, null=True, blank=True)
    cost_centre_code = models.CharField(max_length=20, blank=True)
    eligible_approvers = models.ManyToManyField(USER, blank=True, related_name="+")
    escalated_to_admins = models.BooleanField(default=False)
    state = models.CharField(max_length=14, choices=RoundState.choices, default=RoundState.PENDING)
    decided_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    reminded_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["request", "round_number"]
        constraints = [
            models.UniqueConstraint(fields=["request", "round_number"], name="uniq_round_per_request"),
            # only one open (PENDING or HELD) round per request
            models.UniqueConstraint(
                fields=["request"],
                condition=models.Q(state__in=["PENDING", "HELD"]),
                name="uniq_open_round_per_request",
            ),
        ]

    def __str__(self):
        return f"{self.request.reference} round {self.round_number} ({self.state})"


class RequestEvent(models.Model):
    """Immutable log of everything that happens to a request.

    The audit trail is every row; the conversation panel is the rows with `in_conversation=True`.
    A decision (approve / reject / return / resubmit) is one row with the reason in `note`.
    """

    request = models.ForeignKey(ShipmentRequest, on_delete=models.PROTECT, related_name="events")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_role = models.CharField(max_length=20, choices=ACTOR_ROLE_CHOICES, default=SYSTEM_ACTOR)
    kind = models.CharField(max_length=10, choices=EventKind.choices, default=EventKind.EVENT)
    in_conversation = models.BooleanField(default=False)
    action = models.CharField(max_length=60)
    from_status = models.CharField(max_length=20, choices=Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Status.choices, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["at", "id"]

    def __str__(self):
        return f"{self.request.reference}: {self.action}"
