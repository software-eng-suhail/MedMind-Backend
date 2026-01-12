from django.contrib import admin
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils.html import format_html
from django.contrib import messages
from unfold.admin import ModelAdmin

from .models import BiopsyResult, BiopsyResultPending, BiopsyResultStatus


class BiopsyResultAdmin(ModelAdmin):
	list_display = (
		'id',
		'checkup_display',
		'status_badge',
		'verified_by',
		'uploaded_at',
		'credits_refunded',
	)
	search_fields = (
		'result',
		'object_id',
		'verified_by__username',
		'verified_by__email',
	)
	list_filter = (
		'status',
		'credits_refunded',
		'uploaded_at',
	)
	readonly_fields = ('status', 'verified_by', 'uploaded_at')
	list_per_page = 25

	def checkup_display(self, obj):
		return f"{obj.content_type}#{obj.object_id}"

	checkup_display.short_description = 'Checkup'

	def status_badge(self, obj):
		color_class = {
			BiopsyResultStatus.PENDING: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400',
			BiopsyResultStatus.VERIFIED: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
			BiopsyResultStatus.REJECTED: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
		}.get(obj.status, 'bg-base-100 text-base-700 dark:bg-base-500/20 dark:text-base-200')
		return format_html(
			'<span class="inline-block font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap {}">{}</span>',
			color_class,
			obj.get_status_display(),
		)

	status_badge.short_description = 'Status'


@admin.register(BiopsyResultPending)
class BiopsyResultPendingAdmin(ModelAdmin):
	list_display = (
		'id',
		'checkup_display',
		'status_badge',
		'verified_by',
		'uploaded_at',
		'verify_action',
	)
	search_fields = (
		'object_id',
		'result',
	)
	list_filter = (
		'uploaded_at',
	)
	readonly_fields = ('status', 'verified_by', 'uploaded_at')
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
		return qs.filter(status=BiopsyResultStatus.PENDING)

	def checkup_display(self, obj):
		return f"{obj.content_type}#{obj.object_id}"

	checkup_display.short_description = 'Checkup'

	def status_badge(self, obj):
		return format_html(
			'<span class="inline-block font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400">{}</span>',
			obj.get_status_display(),
		)

	status_badge.short_description = 'Status'

	def verify_action(self, obj):
		url = reverse('admin:biopsy_result_biopsyresultpending_verify', args=[obj.pk])
		return format_html(
			'<a href="{}" class="bg-primary-600 border border-transparent font-medium px-3 py-2 rounded-default text-sm text-white">Verify</a>',
			url,
		)

	verify_action.short_description = 'Action'
	verify_action.allow_tags = True

	def get_urls(self):
		urls = super().get_urls()
		custom = [
			path('verify/<int:pk>/', self.admin_site.admin_view(self.verify_view), name='biopsy_result_biopsyresultpending_verify'),
		]
		return custom + urls

	def verify_view(self, request, pk):
		try:
			obj = BiopsyResultPending.objects.get(pk=pk)
		except BiopsyResultPending.DoesNotExist:
			messages.error(request, 'Biopsy result not found.')
			return redirect('admin:biopsy_result_biopsyresultpending_changelist')

		obj.status = BiopsyResultStatus.VERIFIED
		obj.verified_by = request.user if request.user.is_authenticated else None
		obj.save(update_fields=['status', 'verified_by'])
		messages.success(request, f"Biopsy result {obj.pk} verified.")
		return redirect('admin:biopsy_result_biopsyresultpending_changelist')


admin.site.register(BiopsyResult, BiopsyResultAdmin)