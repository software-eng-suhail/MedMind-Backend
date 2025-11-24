from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, DoctorProfile, AdminProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a role-specific profile when a User is created.

    This uses `get_or_create` to be idempotent. Profiles no longer have
    separate `doctor_id`/`admin_id` fields; the profile primary key is
    available as `profile.pk` if you need a numeric identifier.
    """
    if not created:
        return

    if instance.role == User.Role.DOCTOR:
        DoctorProfile.objects.get_or_create(user=instance)
    elif instance.role == User.Role.ADMIN:
        AdminProfile.objects.get_or_create(user=instance)
