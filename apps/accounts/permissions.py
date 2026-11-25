"""Permission map in code (not a table): what each of the four roles may do, per area.

Object-level rules (owner, eligible approver, ...) stay in the services; this map answers
"may this role use this area at all?" and is enforced on every endpoint with `HasPermission`.
Editable later only if Diasorin asks.
"""

from rest_framework.permissions import BasePermission

from .enums import AppRole
from .services.roles import roles_for

REQUESTER, APPROVER = AppRole.REQUESTER.value, AppRole.APPROVER.value
CUSTOMER_MANAGEMENT, ADMIN = AppRole.CUSTOMER_MANAGEMENT.value, AppRole.ADMIN.value

# Requests are never deleted, only cancelled (owner-level for requester/approver/CM, any open request for admin).
ACTIONS = ("view", "create", "edit", "delete", "cancel", "decide", "manage")

AREAS = (
    "requests",
    "approvals",
    "workbench",
    "admin.access",
    "admin.users",
    "admin.cost_centres",
    "admin.rules",
    "admin.notifications",
    "admin.master_data",
    "admin.oversight",
    "admin.audit",
    "admin.configuration",
)


def _grant(**actions: bool) -> dict[str, bool]:
    return {a: actions.get(a, False) for a in ACTIONS}


NONE = _grant()
ADMIN_AREA = _grant(view=True, manage=True)

PERMISSIONS: dict[str, dict[str, dict[str, bool]]] = {
    REQUESTER: {
        "requests": _grant(view=True, create=True, edit=True, cancel=True),  # own requests (object-level)
        "approvals": NONE,
        "workbench": NONE,
        **{f"admin.{a}": NONE for a in (
            "access", "users", "cost_centres", "rules", "notifications",
            "master_data", "oversight", "audit", "configuration",
        )},
    },
    APPROVER: {
        "requests": _grant(view=True, create=True, edit=True, cancel=True),
        "approvals": _grant(view=True, decide=True),
        "workbench": NONE,
        **{f"admin.{a}": NONE for a in (
            "access", "users", "cost_centres", "rules", "notifications",
            "master_data", "oversight", "audit", "configuration",
        )},
    },
    CUSTOMER_MANAGEMENT: {
        "requests": _grant(view=True, create=True, edit=True, cancel=True),
        "approvals": NONE,
        "workbench": _grant(view=True, edit=True, decide=True, manage=True),
        **{f"admin.{a}": NONE for a in (
            "access", "users", "cost_centres", "rules", "notifications",
            "master_data", "oversight", "audit", "configuration",
        )},
    },
    ADMIN: {
        "requests": _grant(view=True, create=True, edit=True, cancel=True, manage=True),
        "approvals": _grant(view=True, decide=True),
        "workbench": _grant(view=True, edit=True, decide=True, manage=True),
        **{f"admin.{a}": ADMIN_AREA for a in (
            "access", "users", "cost_centres", "rules", "notifications",
            "master_data", "oversight", "audit", "configuration",
        )},
    },
}  # fmt: skip


def has_permission(user, area: str, action: str) -> bool:
    """True if any of the user's roles grants `action` on `area`."""
    if not user or not user.is_authenticated:
        return False
    return any(PERMISSIONS[role].get(area, {}).get(action, False) for role in roles_for(user))


def effective_permissions(user) -> dict[str, dict[str, bool]]:
    """The merged map for this user (a permission is granted if any of their roles grants it)."""
    held = roles_for(user)
    return {area: {a: any(PERMISSIONS[r][area][a] for r in held) for a in ACTIONS} for area in AREAS}


class HasPermission(BasePermission):
    """DRF permission: `permission_classes = [HasPermission("admin.users", "view")]`-style.

    Use `HasPermission.require(area, action)` to get a class DRF can instantiate.
    """

    area = ""
    action = ""

    def has_permission(self, request, view):
        return has_permission(request.user, self.area, self.action)

    @classmethod
    def require(cls, area: str, action: str) -> type["HasPermission"]:
        return type(
            f"HasPermission_{area}_{action}".replace(".", "_"), (cls,), {"area": area, "action": action}
        )
