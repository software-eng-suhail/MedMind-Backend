import time

from django.contrib.auth import authenticate
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from user.models import User
from user.serializers import (
	AdminSerializer,
	AdminWriteSerializer,
	DoctorSerializer,
	DoctorWriteSerializer,
	LoginSerializer,
)


class DoctorViewSet(viewsets.ModelViewSet):
	queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser, JSONParser]

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return DoctorWriteSerializer
		return DoctorSerializer

	def perform_destroy(self, instance):
		try:
			instance.doctor_profile.delete()
		except Exception:
			pass
		instance.delete()


class AdminViewSet(viewsets.ModelViewSet):
	queryset = User.objects.filter(role=User.Role.ADMIN).select_related('admin_profile')
	permission_classes = [permissions.IsAuthenticated]

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


class AuthViewSet(viewsets.ViewSet):
	permission_classes = [permissions.AllowAny]
	parser_classes = [MultiPartParser, FormParser, JSONParser]

	class DoctorIdSerializer(serializers.Serializer):
		doctor_id = serializers.IntegerField(required=True)

	class EmptySerializer(serializers.Serializer):
		pass

	serializer_action_classes = {
		'signup_doctor': DoctorWriteSerializer,
		'login': LoginSerializer,
		'logout': EmptySerializer,
		'verify_email': EmptySerializer,
		'verify_doctor': DoctorIdSerializer,
		'suspend_doctor': DoctorIdSerializer,
	}

	def get_serializer_class(self):
		return self.serializer_action_classes.get(self.action)

	def get_serializer(self, *args, **kwargs):
		serializer_class = self.get_serializer_class()
		if serializer_class is None:
			return None
		kwargs.setdefault('context', self.get_serializer_context())
		return serializer_class(*args, **kwargs)

	def get_serializer_context(self):
		return {'request': self.request, 'format': self.format_kwarg, 'view': self}

	@action(detail=False, methods=['post'], url_path='signup/doctor')
	def signup_doctor(self, request):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()

		refresh = RefreshToken.for_user(user)
		data = {
			'doctor': DoctorSerializer(user, context={'request': request}).data,
		}
		return Response(status=status.HTTP_201_CREATED)

	@action(detail=False, methods=['post'], url_path='login')
	def login(self, request):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		username = serializer.validated_data.get('username') or serializer.validated_data.get('email')
		password = serializer.validated_data['password']

		user = authenticate(request, username=username, password=password)
		if user is None:
			try:
				u = User.objects.get(email=username)
			except User.DoesNotExist:
				return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
			user = authenticate(request, username=u.username, password=password)
			if user is None:
				return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

		if not user.is_doctor():
			return Response({'detail': 'User is not a doctor'}, status=status.HTTP_403_FORBIDDEN)

		profile = getattr(user, 'doctor_profile', None)
		if profile:
			profile.logged_in = True
			profile.save(update_fields=['logged_in'])

		refresh = RefreshToken.for_user(user)
		data = {
			'refresh': str(refresh),
			'access': str(refresh.access_token),
			'doctor': DoctorSerializer(user, context={'request': request}).data,
		}
		return Response(data)

	@action(detail=False, methods=['post'], url_path='logout', permission_classes=[permissions.IsAuthenticated])
	def logout(self, request):
		user = request.user
		if user.is_doctor():
			profile = getattr(user, 'doctor_profile', None)
			if profile:
				profile.logged_in = False
				profile.save(update_fields=['logged_in'])
		return Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)

	@action(detail=False, methods=['post'], url_path='verify-email')
	def verify_email(self, request):
		user = request.user

		profile = getattr(user, 'doctor_profile', None)
		if profile:
			from user.models import EmailVerificationStatus
			profile.email_verification_status = EmailVerificationStatus.VERIFIED
			profile.save(update_fields=['email_verification_status'])
			return Response({'detail': 'Email verified successfully.'}, status=status.HTTP_200_OK)

		return Response({'detail': 'Doctor profile not found.'}, status=status.HTTP_400_BAD_REQUEST)

	@action(detail=False, methods=['post'], url_path='verify-doctor', permission_classes=[permissions.IsAdminUser])
	def verify_doctor(self, request):
		serializer = self.get_serializer(data=request.data)
		if serializer:
			serializer.is_valid(raise_exception=True)
			doctor_id = serializer.validated_data['doctor_id']
		else:
			doctor_id = request.data.get('doctor_id')
			if not doctor_id:
				return Response({'detail': 'doctor_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

		try:
			doctor = User.objects.get(pk=doctor_id, role=User.Role.DOCTOR)
		except User.DoesNotExist:
			return Response({'detail': 'Doctor not found.'}, status=status.HTTP_404_NOT_FOUND)

		profile = getattr(doctor, 'doctor_profile', None)
		if profile:
			from user.models import DoctorAccountStatus
			profile.account_status = DoctorAccountStatus.VERIFIED
			profile.save(update_fields=['account_status'])
			return Response({'detail': f'Doctor {doctor.username} verified successfully.'}, status=status.HTTP_200_OK)

		return Response({'detail': 'Doctor profile not found.'}, status=status.HTTP_400_BAD_REQUEST)

	@action(detail=False, methods=['post'], url_path='suspend-doctor', permission_classes=[permissions.IsAdminUser])
	def suspend_doctor(self, request):
		serializer = self.get_serializer(data=request.data)
		if serializer:
			serializer.is_valid(raise_exception=True)
			doctor_id = serializer.validated_data['doctor_id']
		else:
			doctor_id = request.data.get('doctor_id')
			if not doctor_id:
				return Response({'detail': 'doctor_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

		try:
			doctor = User.objects.get(pk=doctor_id, role=User.Role.DOCTOR)
		except User.DoesNotExist:
			return Response({'detail': 'Doctor not found.'}, status=status.HTTP_404_NOT_FOUND)

		profile = getattr(doctor, 'doctor_profile', None)
		if profile:
			from user.models import DoctorAccountStatus
			profile.account_status = DoctorAccountStatus.SUSPENDED
			profile.save(update_fields=['account_status'])
			return Response({'detail': f'Doctor {doctor.username} suspended successfully.'}, status=status.HTTP_200_OK)

		return Response({'detail': 'Doctor profile not found.'}, status=status.HTTP_400_BAD_REQUEST)
