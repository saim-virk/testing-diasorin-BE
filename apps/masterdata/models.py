from datetime import date

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .enums import Destination, Hazard, ReasonScopeGroup, Temperature


class Country(models.Model):
    iso2 = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=10, choices=Destination.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return f"{self.name} ({self.iso2})"


class PVARICode(models.Model):
    code = models.CharField(max_length=10, unique=True)
    description_it = models.CharField(max_length=255)
    description_en = models.CharField(max_length=255)
    un_number = models.CharField(max_length=10, blank=True)
    hazard = models.CharField(max_length=12, choices=Hazard.choices)
    default_temperature = models.CharField(max_length=10, choices=Temperature.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "PVARI code"
        verbose_name_plural = "PVARI codes"

    def __str__(self):
        return f"{self.code} — {self.description_en}"


class ReasonCode(models.Model):
    scope_group = models.CharField(max_length=10, choices=ReasonScopeGroup.choices)
    code = models.CharField(max_length=10)
    description_it = models.CharField(max_length=255)
    description_en = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["scope_group", "id"]
        constraints = [
            models.UniqueConstraint(fields=["scope_group", "code"], name="uniq_reasoncode_group_code"),
        ]

    @property
    def print_language(self) -> str:
        """Language printed on shipping documents (URS footnote 2)."""
        return "it" if self.scope_group == ReasonScopeGroup.ITALY else "en"

    def __str__(self):
        return f"{self.code} — {self.description_en}"


class ShipsFromSite(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    applies_calendar = models.BooleanField(default=False)
    # Weekdays this site ships on: 0 = Monday ... 6 = Sunday. Ignored when applies_calendar is False.
    allowed_weekdays = ArrayField(
        models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(6)]),
        default=list,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        days = self.allowed_weekdays or []
        if len(days) != len(set(days)):
            raise ValidationError({"allowed_weekdays": "Each weekday may appear only once."})

    def allows_ship_day(self, day: date) -> bool:
        """Read from the database row at validation time, never cached (AC-03.03.4)."""
        if not self.applies_calendar:
            return True
        return day.weekday() in (self.allowed_weekdays or [])

    def __str__(self):
        return self.name


class PackagingType(models.Model):
    code = models.CharField(max_length=20, unique=True)
    dimensions = models.CharField(max_length=60, blank=True)
    description = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.code} ({self.dimensions})"


class Branch(models.Model):
    """Recipient code. SAMPLE data until the real master list arrives (W3)."""

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    scope = models.CharField(max_length=10, choices=Destination.choices)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # PO number is mandatory for this branch when SiteConfig.po_mandatory_us is on (DS Inc, SOP 15.0016).
    po_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "branches"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Carrier(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class CostCentre(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    approval_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class CostCentreApprover(models.Model):
    cost_centre = models.ForeignKey(CostCentre, on_delete=models.CASCADE, related_name="approvers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="approver_for")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cost_centre", "user"], name="uniq_costcentre_approver"),
        ]

    def __str__(self):
        return f"{self.user} approves {self.cost_centre.code}"
