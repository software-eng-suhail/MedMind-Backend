from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import redirect
from django.contrib import messages

from .models import User, AdminProfile, DoctorProfile, DoctorProfileToVerify, DoctorAccountStatus


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
	list_display = ('username', 'email', 'role', 'is_staff', 'is_active')


admin.site.register(AdminProfile)
admin.site.register(DoctorProfile)


@admin.register(DoctorProfileToVerify)
class AccountsVerifyingAdmin(admin.ModelAdmin):
	list_display = ('user', 'email', 'account_status', 'verify_action')
	search_fields = ('user__username', 'user__email', 'user__name')
	list_per_page = 25
	actions = None

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		# Disable editing via change form; verification handled via custom action
		return False

	def has_delete_permission(self, request, obj=None):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.filter(account_status=DoctorAccountStatus.NOT_VERIFIED)

	def email(self, obj):
		return getattr(obj.user, 'email', '')

	def verify_action(self, obj):
		url = reverse('admin:user_doctorprofiletoverify_verify', args=[obj.pk])
		return format_html('<a class="button" href="{}">Verify</a>', url)
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
		messages.success(request, f"Doctor '{obj.user.username}' verified.")
		return redirect('admin:user_doctorprofiletoverify_changelist')