from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .enums import AppRole
from .models import BlockedEmail, RoleAssignment, User


@receiver(post_delete, sender=RoleAssignment)
def end_sessions_when_a_role_is_removed(sender, instance, **kwargs):
    """Removing a role signs the person out (service, Django Admin or shell). Adding one does not."""
    User.objects.filter(pk=instance.user_id).update(sessions_revoked_at=timezone.now())


@receiver(post_save, sender=BlockedEmail)
def end_sessions_when_an_address_is_blocked(sender, instance, **kwargs):
    """Blocking an address signs that person out, however the row was added (service, Django Admin, shell)."""
    User.objects.filter(email__iexact=instance.email).update(sessions_revoked_at=timezone.now())


@receiver([post_save, post_delete], sender=RoleAssignment)
def keep_admin_flags_in_sync(sender, instance, **kwargs):
    """Role changes made anywhere (service, Django Admin, shell) keep is_staff/is_superuser in step."""
    if instance.role == AppRole.ADMIN:
        from .services.roles import sync_admin_flags

        sync_admin_flags(instance.user)
