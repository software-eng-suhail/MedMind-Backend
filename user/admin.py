from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group
from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from unfold.admin import ModelAdmin, StackedInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import (
	User,
	AdminProfile,
	DoctorProfile,
	DoctorProfileToVerify,
	DoctorAccountStatus,
	AdminUser,
	DoctorUser,
)

# Register Groups using Unfold-styled admin
try:
	admin.site.unregister(Group)
except admin.sites.NotRegistered:
	pass


class UnfoldGroupAdmin(DjangoGroupAdmin, ModelAdmin):
	list_per_page = 25


admin.site.register(Group, UnfoldGroupAdmin)


class AdminProfileInline(StackedInline):
	model = AdminProfile
	can_delete = False
	extra = 0
	fk_name = 'user'


class DoctorProfileInline(StackedInline):
	model = DoctorProfile
	can_delete = False
	extra = 0
	fk_name = 'user'



class BaseProxyUserAdmin(BaseUserAdmin, ModelAdmin):
	# Use Unfold forms for proper styling
	form = UserChangeForm
	add_form = UserCreationForm
	change_password_form = AdminPasswordChangeForm
	# Common config
	search_fields = ('username', 'email', 'name')
	list_per_page = 25
	# Keep `role` read-only within proxies
	readonly_fields = ('role',)


@admin.register(AdminUser)
class AdminUserAdmin(BaseProxyUserAdmin):
	list_display = ('username', 'email', 'is_staff', 'is_active', 'created_at')
	list_filter = ('is_active', 'is_staff')
	inlines = [AdminProfileInline]

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.filter(role=User.Role.ADMIN)


@admin.register(DoctorUser)
class DoctorUserAdmin(BaseProxyUserAdmin):
	list_display = ('username', 'email', 'is_active', 'created_at', 'is_verified_doctor')
	list_filter = ('is_active',)
	inlines = [DoctorProfileInline]

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.filter(role=User.Role.DOCTOR)


@admin.register(DoctorProfileToVerify)
class AccountsVerifyingAdmin(ModelAdmin):
	list_display = ('user', 'email', 'status_badge', 'verify_action')
	search_fields = ('user__username', 'user__email', 'user__name')
	list_per_page = 25
	actions = None

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.filter(account_status=DoctorAccountStatus.NOT_VERIFIED)

	def email(self, obj):
		return getattr(obj.user, 'email', '')

	def status_badge(self, obj):
		# Unfold-style label for account status (warning)
		status_text = obj.get_account_status_display()
		return format_html(
			'<span class="inline-block font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400">{}</span>',
			status_text,
		)

	status_badge.short_description = 'Account status'

	def verify_action(self, obj):
		url = reverse('admin:user_doctorprofiletoverify_verify', args=[obj.pk])
		# Unfold primary button style as a link
		return format_html(
			'<a href="{}" class="bg-primary-600 border border-transparent font-medium px-3 py-2 rounded-default text-sm text-white">Verify</a>',
			url,
		)
	verify_action.short_description = 'Action'
	verify_action.allow_tags = True

	def get_urls(self):
		urls = super().get_urls()
		custom = [
			path('verify/<int:pk>/', self.admin_site.admin_view(self.verify_view), name='user_doctorprofiletoverify_verify'),
		]
		return custom + urls

	def verify_view(self, request, pk):
		try:
			obj = DoctorProfileToVerify.objects.select_related('user').get(pk=pk)
		except DoctorProfileToVerify.DoesNotExist:
			messages.error(request, 'Doctor profile not found.')
			return redirect('admin:user_doctorprofiletoverify_changelist')

		obj.account_status = DoctorAccountStatus.VERIFIED
		obj.save(update_fields=['account_status'])

		# Try to notify the doctor via email about verification
		email = getattr(obj.user, 'email', None)
		if email:
			try:
				subject = 'Your MedMind doctor account is verified'
				body = (
					f'Hello {obj.user.username or obj.user.email},\n\n'
					'Your doctor account has been verified and is now active.\n'
					'You can log in and start using MedMind.\n\n'
					'Thank you!'
				)
				send_mail(subject, body, settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER, [email], fail_silently=True)
			except Exception:
				pass
		messages.success(request, f"Doctor '{obj.user.username}' verified.")
		return redirect('admin:user_doctorprofiletoverify_changelist')