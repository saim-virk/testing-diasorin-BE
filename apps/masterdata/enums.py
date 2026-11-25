from django.db import models


class Destination(models.TextChoices):
    ITALY = "ITALY", "Italy"
    EU = "EU", "EU"
    EXTRA_EU = "EXTRA_EU", "Extra-EU"
    USA = "USA", "USA"


class ReasonScopeGroup(models.TextChoices):
    ITALY = "ITALY", "Italy"
    EU_EXTRA = "EU_EXTRA", "EU / Extra-EU / USA"


class Temperature(models.TextChoices):
    AMBIENT = "AMBIENT", "Ambient"
    COOL_2_8 = "COOL_2_8", "+2 +8 °C"
    DRY_ICE = "DRY_ICE", "Dry ice"


# Strictness order: DRY_ICE > COOL_2_8 > AMBIENT
TEMPERATURE_RANK = {Temperature.AMBIENT: 0, Temperature.COOL_2_8: 1, Temperature.DRY_ICE: 2}


class Currency(models.TextChoices):
    """Fixed list for standard prices on request lines (was a table)."""

    EUR = "EUR", "EUR"
    USD = "USD", "USD"
    GBP = "GBP", "GBP"
    CHF = "CHF", "CHF"
    JPY = "JPY", "JPY"
    CNY = "CNY", "CNY"
    CAD = "CAD", "CAD"
    AUD = "AUD", "AUD"
    SEK = "SEK", "SEK"
    DKK = "DKK", "DKK"
    NOK = "NOK", "NOK"
    PLN = "PLN", "PLN"
    CZK = "CZK", "CZK"
    HUF = "HUF", "HUF"


class Hazard(models.TextChoices):
    UNINFECTED = "UNINFECTED", "Uninfected"
    INFECTIOUS = "INFECTIOUS", "Infectious"


def destination_for_scope_group(destination: str) -> str:
    """Reason-code list used for a destination (USA shares the EU / Extra-EU list)."""
    return ReasonScopeGroup.ITALY if destination == Destination.ITALY else ReasonScopeGroup.EU_EXTRA
