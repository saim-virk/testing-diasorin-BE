"""Values derived from the lines (REQUIREMENTS section 3, step 3 / 4). Mirrored by the frontend's derive.ts."""

from decimal import Decimal

from apps.masterdata.enums import TEMPERATURE_RANK, Hazard

from ..enums import DangerousFeatures


def pvari_lines(lines):
    return [ln for ln in lines if ln.pvari_ref_id or ln.pvari_code]


def un_numbers(lines) -> list[str]:
    """UN numbers of the lines, de-duplicated, in line order."""
    seen: list[str] = []
    for ln in lines:
        if ln.un_number and ln.un_number not in seen:
            seen.append(ln.un_number)
    return seen


def overall_temperature(lines) -> str | None:
    """The strictest transport temperature of the lines: dry ice > +2 +8 > ambient."""
    temps = [ln.temperature for ln in lines if ln.temperature in TEMPERATURE_RANK]
    return max(temps, key=lambda t: TEMPERATURE_RANK[t]) if temps else None


def total_weight(lines) -> Decimal:
    return sum((ln.net_weight_kg or Decimal(0) for ln in lines), Decimal(0))


def derived_hazard(lines) -> str | None:
    """INFECTIOUS if any PVARI line is infectious, UNINFECTED if there are PVARI lines and none is,
    None when there is no PVARI line (the requester then chooses)."""
    coded = pvari_lines(lines)
    if not coded:
        return None
    if any(ln.hazard == Hazard.INFECTIOUS for ln in coded):
        return DangerousFeatures.INFECTIOUS
    return DangerousFeatures.UNINFECTED


def allowed_dangerous_features(lines) -> list[str]:
    """INFECTIOUS lock: nothing else is allowed. Uninfected PVARI lines: Uninfected or Other hazards
    (Other is only selectable when the lines are not derived as infectious). No PVARI line: free choice."""
    derived = derived_hazard(lines)
    if derived == DangerousFeatures.INFECTIOUS:
        return [DangerousFeatures.INFECTIOUS]
    if derived == DangerousFeatures.UNINFECTED:
        return [DangerousFeatures.UNINFECTED, DangerousFeatures.OTHER]
    return [d.value for d in DangerousFeatures]


def derived_summary(req, lines=None) -> dict:
    lines = list(req.lines.all()) if lines is None else lines
    return {
        "un_numbers": un_numbers(lines),
        "hazard": derived_hazard(lines),
        "overall_temperature": overall_temperature(lines),
        "total_weight_kg": total_weight(lines),
        "line_count": len(lines),
        "dangerous_features_locked": derived_hazard(lines) == DangerousFeatures.INFECTIOUS,
    }
