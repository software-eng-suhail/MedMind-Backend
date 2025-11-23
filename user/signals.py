from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, DoctorProfile, AdminProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a role-specific profile when a User is created.

    This uses get_or_create to be idempotent and assigns sequential
    `doctor_id`/`admin_id` from the profile primary key when missing.
    """
    if not created:
        return

    if instance.role == User.Role.DOCTOR:
        profile, _ = DoctorProfile.objects.get_or_create(user=instance)
        if not profile.doctor_id:
            profile.doctor_id = profile.pk
            profile.save()
    elif instance.role == User.Role.ADMIN:
        profile, _ = AdminProfile.objects.get_or_create(user=instance)
        if not profile.admin_id:
            profile.admin_id = profile.pk
            profile.save()
