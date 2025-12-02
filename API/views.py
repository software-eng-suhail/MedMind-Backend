from django.shortcuts import render
from rest_framework import generics, permissions, viewsets, serializers
from user.serializers import DoctorSerializer, DoctorWriteSerializer, AdminSerializer, AdminWriteSerializer
from user.models import User, DoctorProfile, AdminProfile
from rest_framework.decorators import action
from rest_framework.response import Response

# imports for the apps we're adding endpoints for
from AI_Engine.models import ImageSample, ImageResult
from AI_Engine.serializers import ImageSampleSerializer, ImageResultReadSerializer, ImageResultWriteSerializer
from biopsy_result.models import BiopsyResult
from biopsy_result.serializers import BiopsyResultSerializer
from checkup.models import Checkup, SkinCancerCheckup
from checkup.serializers import CheckupSerializer, SkinCancerCheckupSerializer


class DoctorViewSet(viewsets.ModelViewSet):
	"""ViewSet to create/update/delete/list doctors.

	- Read (list/retrieve) uses `DoctorSerializer` (includes profile read-only fields).
	- Write (create/update) uses `DoctorWriteSerializer` which handles `password` and profile fields.
	"""
	queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
	permission_classes = [permissions.AllowAny]

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return DoctorWriteSerializer
		return DoctorSerializer

	def perform_destroy(self, instance):
		# remove associated profile then user
		try:
			instance.doctor_profile.delete()
		except Exception:
			pass
		instance.delete()

	@action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
	def public_list(self, request):
		"""Optional public list of doctors (duplicated endpoint)"""
		qs = self.get_queryset()
		page = self.paginate_queryset(qs)
		if page is not None:
			serializer = DoctorSerializer(page, many=True)
			return self.get_paginated_response(serializer.data)
		serializer = DoctorSerializer(qs, many=True)
		return Response(serializer.data)


class AdminViewSet(viewsets.ModelViewSet):
	"""ViewSet to manage admin users."""
	queryset = User.objects.filter(role=User.Role.ADMIN).select_related('admin_profile')
	permission_classes = [permissions.AllowAny]

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return AdminWriteSerializer
		return AdminSerializer

	def perform_destroy(self, instance):
		try:
			instance.admin_profile.delete()
		except Exception:
			pass
		instance.delete()


# --- New viewsets for AI_Engine, biopsy_result, and checkup ---


class CheckupViewSet(viewsets.ModelViewSet):
	queryset = Checkup.objects.select_related('doctor').prefetch_related('image_samples', 'skin_cancer')
	permission_classes = [permissions.AllowAny]
	serializer_class = CheckupSerializer

	def create(self, request, *args, **kwargs):
		# Prevent creating bare Checkup instances. Clients should create subtype checkups
		# (e.g. POST /skin-cancer/) which will create both the base Checkup and the subtype.
		raise serializers.ValidationError(
			"Create checkups via subtype endpoints (for example POST /skin-cancer/)."
		)


class SkinCancerCheckupViewSet(viewsets.ModelViewSet):
	queryset = SkinCancerCheckup.objects.select_related('checkup')
	permission_classes = [permissions.AllowAny]
	serializer_class = SkinCancerCheckupSerializer

	def create(self, request, *args, **kwargs):
		"""Create a SkinCancerCheckup. Accepts either:
		- `checkup`: an existing Checkup PK, or
		- inline checkup fields (age, gender, blood_type, note, doctor) which will create the base Checkup.

		The method validates and creates both objects inside a transaction.
		"""
		from django.db import transaction

		data = request.data.copy()
		checkup_pk = data.get('checkup')

		with transaction.atomic():
			if checkup_pk:
				try:
					checkup = Checkup.objects.get(pk=checkup_pk)
				except Checkup.DoesNotExist:
					raise serializers.ValidationError({'checkup': 'Checkup not found'})

				# ensure not already a skin cancer record
				if hasattr(checkup, 'skin_cancer'):
					raise serializers.ValidationError({'checkup': 'This checkup already has a SkinCancerCheckup.'})
			else:
				# create a base Checkup from provided fields
				checkup_fields = {}
				for f in ['age', 'gender', 'blood_type', 'note', 'status']:
					if f in data:
						checkup_fields[f] = data.pop(f)

				# set doctor: prefer explicit id, otherwise use authenticated user
				doctor_id = data.get('doctor')
				if doctor_id:
					from user.models import User as UserModel
					try:
						checkup_fields['doctor'] = UserModel.objects.get(pk=doctor_id)
					except UserModel.DoesNotExist:
						raise serializers.ValidationError({'doctor': 'Doctor not found'})
				else:
					if request.user and request.user.is_authenticated:
						checkup_fields['doctor'] = request.user
					else:
						raise serializers.ValidationError({'doctor': 'Provide doctor id or authenticate as a doctor'})

				checkup = Checkup.objects.create(**checkup_fields)

			# Build serializer payload for the SkinCancerCheckup
			payload = {
				'checkup': checkup.pk,
				'lesion_size_mm': data.get('lesion_size_mm'),
				'lesion_location': data.get('lesion_location'),
				'asymmetry': data.get('asymmetry'),
				'border_irregularity': data.get('border_irregularity'),
				'color_variation': data.get('color_variation'),
				'diameter_mm': data.get('diameter_mm'),
				'evolution': data.get('evolution'),
			}

			serializer = self.get_serializer(data=payload)
			serializer.is_valid(raise_exception=True)
			instance = serializer.save()
			headers = self.get_success_headers(serializer.data)
			return Response(serializer.data, status=201, headers=headers)


class ImageSampleViewSet(viewsets.ModelViewSet):
	queryset = ImageSample.objects.select_related('checkup')
	permission_classes = [permissions.AllowAny]
	serializer_class = ImageSampleSerializer

	def perform_create(self, serializer):
		# enforce max 5 images per checkup
		checkup = serializer.validated_data.get('checkup')
		if checkup and checkup.image_samples.count() >= 5:
			raise serializers.ValidationError('A maximum of 5 images is allowed per checkup.')
		serializer.save()


class ImageResultViewSet(viewsets.ModelViewSet):
	queryset = ImageResult.objects.select_related('image_sample')
	permission_classes = [permissions.AllowAny]

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return ImageResultWriteSerializer
		return ImageResultReadSerializer


class BiopsyResultViewSet(viewsets.ModelViewSet):
	queryset = BiopsyResult.objects.select_related('checkup', 'verified_by')
	permission_classes = [permissions.AllowAny]
	serializer_class = BiopsyResultSerializer
