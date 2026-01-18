from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator

class DoctorAccountStatus(models.TextChoices):
	VERIFIED = 'VERIFIED', 'Verified'
	SUSPENDED = 'SUSPENDED', 'Suspended'
	NOT_VERIFIED = 'NOT_VERIFIED', 'Not Verified'

class EmailVerificationStatus(models.TextChoices):
	PENDING = 'PENDING', 'Pending'
	VERIFIED = 'VERIFIED', 'Verified'


class User(AbstractUser):
	class Role(models.TextChoices):
		ADMIN = 'admin', 'Admin'
		DOCTOR = 'doctor', 'Doctor'

	# override email to ensure uniqueness for doctor registration flows
	email = models.EmailField('email address', unique=True)
	name = models.CharField(max_length=150)

	role = models.CharField(max_length=20, choices=Role.choices)
	created_at = models.DateTimeField(auto_now_add=True)

	def is_doctor(self):
		return self.role == self.Role.DOCTOR

	def is_admin(self):
		return self.role == self.Role.ADMIN

	def is_verified_doctor(self):
		profile = getattr(self, 'doctor_profile', None)
		return profile.account_status == DoctorAccountStatus.VERIFIED if profile else False

	def is_suspended_doctor(self):
		profile = getattr(self, 'doctor_profile', None)
		return profile.account_status == DoctorAccountStatus.SUSPENDED if profile else False

	def is_verified_email(self):
		profile = getattr(self, 'doctor_profile', None)
		return profile.email_verification_status == EmailVerificationStatus.VERIFIED if profile else False

	def __str__(self):
		return self.get_username() or self.email or str(self.pk)


class AdminProfile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_profile')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"AdminProfile({self.user.get_username()})"


class DoctorProfile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='doctor_profile')
	credits = models.IntegerField(default=1000, validators=[MinValueValidator(0)])

	account_status = models.CharField(
		max_length=20,
		choices=DoctorAccountStatus.choices,
		default=DoctorAccountStatus.NOT_VERIFIED,
	)
	email_verification_status = models.CharField(
		max_length=20, 
		choices=EmailVerificationStatus.choices,
		default=EmailVerificationStatus.PENDING,
	)
	profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
	license_image = models.ImageField(upload_to='licenses/')
	specialization = models.CharField(max_length=255)
	logged_in = models.BooleanField(default=False)
	changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='changed_doctors')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"DoctorProfile({self.user.get_username()})"


class DoctorProfileToVerify(DoctorProfile):
	class Meta:
		proxy = True
		verbose_name = 'Accounts Verifying'
		verbose_name_plural = 'Accounts Verifying'


@receiver(post_save, sender=AdminProfile)
def _set_user_staff_on_adminprofile_create(sender, instance, created, **kwargs):
	if not created:
		return
	user = getattr(instance, 'user', None)
	if user and not user.is_staff:
		user.is_staff = True
		user.save(update_fields=['is_staff'])


# Proxy models to show "Admins" and "Doctors" in admin, filtered views of `User`
class AdminUser(User):
	class Meta:
		proxy = True
		verbose_name = 'Admin'
		verbose_name_plural = 'Admins'


class DoctorUser(User):
	class Meta:
		proxy = True
		verbose_name = 'Doctor'
		verbose_name_plural = 'Doctors'
