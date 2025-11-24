from django.shortcuts import render
from rest_framework import generics, permissions, viewsets
from user.serializers import DoctorSerializer, DoctorWriteSerializer
from user.models import User, DoctorProfile
from rest_framework.decorators import action
from rest_framework.response import Response


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
