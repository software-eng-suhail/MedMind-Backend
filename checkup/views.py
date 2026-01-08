import time

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from AI_Engine.models import ImageResult, ImageSample
from AI_Engine.serializers import ImageResultReadSerializer
from checkup.models import CheckupStatus, SkinCancerCheckup
from checkup.serializers import (
	SkinCancerCheckupCreateSerializer,
	SkinCancerCheckupListSerializer,
	SkinCancerCheckupSerializer,
)


class SkinCancerCheckupViewSet(viewsets.ModelViewSet):
	queryset = SkinCancerCheckup.objects.all().select_related('doctor')
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser, JSONParser]
	filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
	filterset_fields = {
		'doctor': ['exact'],
		'result': ['exact'],
		'created_at': ['gte', 'lte'],
		'gender': ['iexact'],
		'blood_type': ['exact'],
	}
	search_fields = ['note', 'lesion_location', 'doctor__username', 'doctor__name']
	ordering_fields = ['created_at', 'confidence']
	ordering = ['-created_at']

	def get_queryset(self):
		qs = super().get_queryset()
		qs = qs.annotate(confidence=Max('image_samples__result__confidence'))
		user = getattr(self.request, 'user', None)
		if getattr(user, 'is_doctor', lambda: False)():
			qs = qs.filter(doctor=user).exclude(status=CheckupStatus.FAILED)
		return qs

	def get_serializer_class(self):
		if self.action == 'create':
			return SkinCancerCheckupCreateSerializer
		if self.action == 'list':
			return SkinCancerCheckupListSerializer
		# detail and other actions use full serializer
		return SkinCancerCheckupSerializer

	def create(self, request, *args, **kwargs):
		data = request.data.copy()
		user = getattr(request, "user", None)
		if getattr(user, "is_doctor", lambda: False)():
			data["doctor"] = user.pk

		with transaction.atomic():
			serializer = self.get_serializer(data=data)
			serializer.is_valid(raise_exception=True)
			instance = serializer.save()

			# Deduct 100 credits from the doctor for this checkup
			doctor_profile = getattr(instance.doctor, 'doctor_profile', None)
			if not doctor_profile or doctor_profile.credits < 100:
				raise serializers.ValidationError({'detail': 'Insufficient credits'})
			doctor_profile.credits = doctor_profile.credits - 100
			doctor_profile.save(update_fields=['credits'])

			# Attach files directly from request.FILES for robust handling across clients.
			files = request.FILES.getlist('images')
			if files:
				ct = ContentType.objects.get_for_model(instance)
				for file_obj in files:
					ImageSample.objects.create(content_type=ct, object_id=instance.pk, image=file_obj)

		# Enqueue inference task for the new checkup
		from API.tasks import run_inference_for_checkup

		# Ensure status is PENDING (serializer may have set it)
		instance.status = instance.status or CheckupStatus.PENDING
		instance.save(update_fields=['status'])

		try:
			task = run_inference_for_checkup.delay(instance.pk)
			# store the Celery task id for traceability
			instance.task_id = task.id
			instance.save(update_fields=['task_id'])
			task_queued = True
			task_error = None
		except Exception as e:
			# Broker or Celery may be unavailable; avoid raising 500 in the API.
			# Record nothing for task_id and return the created object with a warning.
			task_queued = False
			task_error = str(e)

		out = SkinCancerCheckupSerializer(instance, context=self.get_serializer_context()).data
		if not task_queued:
			out['_task_queued'] = False
			out['_task_error'] = task_error
		headers = self.get_success_headers(out)
		return Response(out, status=status.HTTP_201_CREATED, headers=headers)

	@action(detail=True, methods=['get'], url_path='results', permission_classes=[permissions.IsAuthenticated])
	def results(self, request, pk=None):
		"""Return ImageResult rows for this checkup's images.

		Optional query param `wait` (seconds) will block/poll up to that many
		seconds for the checkup to reach `COMPLETED`. Default wait is 30s.
		"""
		checkup = self.get_object()
		try:
			wait = int(request.query_params.get('wait', 30))
		except (TypeError, ValueError):
			wait = 30
		interval = 1
		deadline = time.time() + max(0, wait)

		# If the checkup is still pending but the previously queued task has failed, re-enqueue inference.
		if checkup.status == CheckupStatus.PENDING and checkup.task_id:
			try:
				from celery.result import AsyncResult
				from API.tasks import run_inference_for_checkup

				task_state = AsyncResult(checkup.task_id).state
				if task_state in ('FAILURE', 'REVOKED'):
					new_task = run_inference_for_checkup.delay(checkup.pk)
					checkup.task_id = new_task.id
					checkup.status = CheckupStatus.PENDING
					checkup.save(update_fields=['task_id', 'status'])
			except Exception:
				# If we cannot check or requeue, proceed with normal polling.
				pass

		# Poll until completed or timeout
		while checkup.status != CheckupStatus.COMPLETED and time.time() < deadline:
			time.sleep(interval)
			checkup.refresh_from_db()

		# Gather results whether completed or timed out
		results_qs = ImageResult.objects.filter(image_sample__content_type__model__icontains='skincancercheckup', image_sample__object_id=checkup.pk).select_related('image_sample')
		serializer = ImageResultReadSerializer(results_qs, many=True, context=self.get_serializer_context())

		if checkup.status != CheckupStatus.COMPLETED:
			return Response({'status': checkup.status, 'task_id': checkup.task_id}, status=status.HTTP_202_ACCEPTED)

		return Response({'status': checkup.status, 'task_id': checkup.task_id, 'results': serializer.data})
