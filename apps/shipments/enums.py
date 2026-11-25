from django.db import models

from apps.accounts.enums import AppRole


class Status(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    REJECTED = "REJECTED", "Rejected"
    TO_VERIFY = "TO_VERIFY", "To verify"
    RETURNED = "RETURNED", "Returned for correction"
    VERIFIED = "VERIFIED", "Verified"
    PACKED = "PACKED", "Picked and packed"
    IN_TRANSIT = "IN_TRANSIT", "In transit"
    DELIVERED = "DELIVERED", "Delivered"
    CANCELLED = "CANCELLED", "Cancelled"


class DangerousFeatures(models.TextChoices):
    UNINFECTED = "UNINFECTED", "Uninfected"
    INFECTIOUS = "INFECTIOUS", "Infectious or potentially infectious"
    OTHER = "OTHER", "Other hazards"


class CreditNote(models.TextChoices):
    YES = "YES", "Yes"
    NA = "NA", "N.A."


class YesNo(models.TextChoices):
    YES = "YES", "Yes"
    NO = "NO", "No"


class MaterialType(models.TextChoices):
    IVD = "IVD", "IVD"
    RAW_MATERIALS = "RAW_MATERIALS", "Raw materials"
    OTHER = "OTHER", "Other"


class RawMaterialKind(models.TextChoices):
    TEST_SAMPLE = "TEST_SAMPLE", "Test sample"
    MAIN_SHIPMENT = "MAIN_SHIPMENT", "Main shipment"


class AttachmentKind(models.TextChoices):
    MSDS = "MSDS", "MSDS"
    COA = "COA", "Certificate of Analysis"
    OTHER = "OTHER", "Other"


class SkipReason(models.TextChoices):
    GLOBAL_OFF = "GLOBAL_OFF", "Approval switched off globally"
    CENTRE_OFF = "CENTRE_OFF", "Approval not required for cost centre"
    REQUESTER_EXEMPT = "REQUESTER_EXEMPT", "Requester is exempt"
    NO_APPROVER_SKIP = "NO_APPROVER_SKIP", "No approver — skipped"
    ADMIN_SKIP = "ADMIN_SKIP", "Skipped by an administrator"
    SELF_AUTO_APPROVED = "SELF_AUTO_APPROVED", "Approved automatically (self)"


class RoundState(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    HELD = "HELD", "Held"
    SUPERSEDED = "SUPERSEDED", "Superseded"


SYSTEM_ACTOR = "system"

# Who performed an event: one of the four roles, or the system (reminders, escalations).
ACTOR_ROLE_CHOICES = [*AppRole.choices, (SYSTEM_ACTOR, "System")]


class EventKind(models.TextChoices):
    EVENT = "EVENT", "Event"
    COMMENT = "COMMENT", "Comment"
    QUESTION = "QUESTION", "Question"
    NOTE = "NOTE", "Note"
