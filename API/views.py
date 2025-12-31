import time

from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework import permissions, serializers, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import connection, DatabaseError
from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend

from AI_Engine.models import ImageResult, ImageSample
from AI_Engine.serializers import ImageResultReadSerializer, ImageResultWriteSerializer, ImageSampleSerializer
from biopsy_result.models import BiopsyResult, BiopsyResultStatus
from biopsy_result.serializers import BiopsyResultUploadSerializer, BiopsyResultReviewSerializer
from checkup.models import CheckupStatus, SkinCancerCheckup
from checkup.serializers import (
    SkinCancerCheckupCreateSerializer,
    SkinCancerCheckupListSerializer,
    SkinCancerCheckupSerializer,
)
from user.models import User
from user.serializers import AdminSerializer, AdminWriteSerializer, DoctorSerializer, DoctorWriteSerializer, LoginSerializer


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        status_report = {'database': 'ok'}
        try:
            connection.ensure_connection()
        except DatabaseError as exc:
            status_report['database'] = f'error: {exc}'

        is_healthy = all(v == 'ok' for v in status_report.values())
        http_status = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({'status': 'ok' if is_healthy else 'degraded', **status_report}, status=http_status)



class DoctorViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
    permission_classes = [permissions.AllowAny]
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

    @action(detail=True, methods=['get'], url_path='checkups', permission_classes=[permissions.AllowAny])
    def checkups(self, request, *args, **kwargs):
        doctor = self.get_object()
        qs = SkinCancerCheckup.objects.filter(doctor=doctor).select_related('doctor')
        
        filter_backend = DjangoFilterBackend()
        qs = filter_backend.filter_queryset(request, qs, self)
        
        search_backend = filters.SearchFilter()
        search_backend.search_fields = ['note', 'lesion_location', 'gender', 'blood_type']
        qs = search_backend.filter_queryset(request, qs, self)
        
        ordering_backend = filters.OrderingFilter()
        ordering_backend.ordering_fields = ['id', 'created_at', 'started_at', 'completed_at', 'confidence']
        ordering_backend.ordering = ['-created_at']
        qs = ordering_backend.filter_queryset(request, qs, self)
        
        qs = qs.annotate(confidence=Max('image_samples__result__confidence'))
        
        serializer = SkinCancerCheckupListSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(serializer.data)



class AdminViewSet(viewsets.ModelViewSet):
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


class SkinCancerCheckupViewSet(viewsets.ModelViewSet):
    queryset = SkinCancerCheckup.objects.all().select_related('doctor')
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
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
        with transaction.atomic():
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

            # Deduct 100 credits from the doctor for this checkup
            doctor_profile = getattr(instance.doctor, 'doctor_profile', None)
            if doctor_profile:
                doctor_profile.credits = (doctor_profile.credits) - 100
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

    @action(detail=True, methods=['get'], url_path='results', permission_classes=[permissions.AllowAny])
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


class BiopsyResultViewSet(viewsets.ModelViewSet):
    queryset = BiopsyResult.objects.select_related('content_type', 'verified_by')
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return BiopsyResultUploadSerializer
        return BiopsyResultReviewSerializer

    @action(detail=True, methods=['post'], url_path='verify', permission_classes=[permissions.IsAdminUser])
    def verify(self, request, pk=None):
        """Mark biopsy result as verified, set verifier, refund doctor credits atomically."""
        biopsy = self.get_object()
        admin_user = request.user
        # Defensive: ensure user is an admin per custom role
        if not getattr(admin_user, 'is_admin', lambda: False)():
            return Response({'detail': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            # Update biopsy status and verifier
            biopsy.status = BiopsyResultStatus.VERIFIED
            biopsy.verified_by = admin_user

            # Refund doctor credits once
            if not biopsy.credits_refunded:
                checkup = getattr(biopsy, 'checkup', None)
                doctor = getattr(checkup, 'doctor', None) if checkup else None
                profile = getattr(doctor, 'doctor_profile', None) if doctor else None
                if profile:
                    profile.credits = (profile.credits) + 100
                    profile.save(update_fields=['credits'])
                biopsy.credits_refunded = True

            biopsy.save(update_fields=['status', 'verified_by', 'credits_refunded'])

        serializer = self.get_serializer(biopsy)
        return Response(serializer.data, status=status.HTTP_200_OK)
