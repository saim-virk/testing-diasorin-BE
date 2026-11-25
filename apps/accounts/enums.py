from django.db import models


class AppRole(models.TextChoices):
    """The one role enum. Requester and approver are computed; the other two are assigned."""

    REQUESTER = "requester", "Requester"
    APPROVER = "approver", "Cost Centre Approver"
    CUSTOMER_MANAGEMENT = "customer_management", "Customer Management"
    ADMIN = "admin", "Administrator"


# Roles an administrator can hand out through RoleAssignment (requester and approver are computed).
ASSIGNABLE_ROLE_CHOICES = [
    (AppRole.CUSTOMER_MANAGEMENT.value, AppRole.CUSTOMER_MANAGEMENT.label),
    (AppRole.ADMIN.value, AppRole.ADMIN.label),
]
