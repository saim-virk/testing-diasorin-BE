"""Configuration audit helpers."""

from ..models import ConfigAuditLog

PUBLISHED_ACTION = "configuration_published"


def unpublished_changes_count() -> int:
    """Audit rows after the latest `configuration_published` row (all rows if never published).

    This is the "unpublished changes" number shown in the Admin Panel (AC-09.12.1).
    """
    last = ConfigAuditLog.objects.filter(action=PUBLISHED_ACTION).order_by("-at", "-id").first()
    qs = ConfigAuditLog.objects.exclude(action=PUBLISHED_ACTION)
    if last is not None:
        qs = qs.filter(at__gt=last.at) | qs.filter(at=last.at, id__gt=last.id)
    return qs.count()
