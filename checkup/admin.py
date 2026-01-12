from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.contenttypes.models import ContentType

from unfold.admin import ModelAdmin
from unfold.datasets import BaseDataset

from .models import SkinCancerCheckup, CheckupStatus
from AI_Engine.models import ImageSample, ImageResult


@admin.register(SkinCancerCheckup)
class SkinCancerCheckupAdmin(ModelAdmin):
	list_display = (
		'id',
		'doctor_link',
		'status_badge',
		'image_count',
		'created_at',
		'result',
		'final_confidence',
	)
	readonly_fields = (
		'age',
		'gender',
		'blood_type',
		'note',
		'checkup_type',
		'status',
		'task_id',
		'started_at',
		'completed_at',
		'error_message',
		'failure_refund',
		'result',
		'final_confidence',
		'created_at',
		'doctor',
		'image_count',
		'lesion_size_mm',
		'lesion_location',
		'asymmetry',
		'border_irregularity',
		'color_variation',
		'diameter_mm',
		'evolution',
	)
	search_fields = (
		'doctor__username',
		'doctor__email',
		'note',
		'result',
	)
	list_filter = (
		'status',
		'created_at',
	)
	list_per_page = 25
	change_form_datasets = []

	def doctor_link(self, obj):
		url = reverse('admin:user_doctoruser_change', args=[obj.doctor.pk])
		return format_html('<a href="{}" class="text-primary-600 dark:text-primary-500">{}</a>', url, obj.doctor.username)

	doctor_link.short_description = 'Doctor'

	def status_badge(self, obj):
		color_class = {
			CheckupStatus.PENDING: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400',
			CheckupStatus.IN_PROGRESS: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
			CheckupStatus.COMPLETED: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
			CheckupStatus.FAILED: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
		}.get(obj.status, 'bg-base-100 text-base-700 dark:bg-base-500/20 dark:text-base-200')
		return format_html(
			'<span class="inline-block font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap {}">{}</span>',
			color_class,
			obj.get_status_display(),
		)

	status_badge.short_description = 'Status'


class ImageSampleDatasetAdmin(ModelAdmin):
	list_display = ('id', 'thumb', 'uploaded_at', 'result_model', 'result_confidence', 'xai_link')
	actions = None
	list_per_page = 25

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		obj_id = getattr(self, 'extra_context', {}).get('object')
		if not obj_id:
			return qs.none()
		ct = ContentType.objects.get_for_model(SkinCancerCheckup)
		return qs.filter(content_type=ct, object_id=obj_id).prefetch_related('result')

	def thumb(self, obj):
		if getattr(obj, 'image', None):
			return format_html('<img src="{}" style="height:80px;" />', obj.image.url)
		return '-'

	thumb.short_description = 'Image'

	def _latest_result(self, obj):
		return obj.result.order_by('-id').first()

	def result_model(self, obj):
		res = self._latest_result(obj)
		return res.model if res else '-'

	result_model.short_description = 'Model'

	def result_confidence(self, obj):
		res = self._latest_result(obj)
		return f"{res.confidence:.2f}" if res and res.confidence is not None else '-'

	result_confidence.short_description = 'Confidence'

	def xai_link(self, obj):
		res = self._latest_result(obj)
		if res and getattr(res, 'xai_image', None):
			return format_html('<a href="{}" target="_blank">View XAI</a>', res.xai_image.url)
		return '-'

	xai_link.short_description = 'XAI'


class ImageSampleDataset(BaseDataset):
	model = ImageSample
	model_admin = ImageSampleDatasetAdmin
	tab = True


# Attach dataset tab to the checkup admin
SkinCancerCheckupAdmin.change_form_datasets = [ImageSampleDataset]
