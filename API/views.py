import time

from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import connection, DatabaseError

from AI_Engine.models import ImageResult, ImageSample
from AI_Engine.serializers import ImageResultReadSerializer, ImageResultWriteSerializer, ImageSampleSerializer
from biopsy_result.models import BiopsyResult
from biopsy_result.serializers import BiopsyResultSerializer
from checkup.models import CheckupStatus, SkinCancerCheckup
from checkup.serializers import (
    SkinCancerCheckupCreateSerializer,
    SkinCancerCheckupListSerializer,
    SkinCancerCheckupSerializer,
)
from user.models import User
from user.serializers import AdminSerializer, AdminWriteSerializer, DoctorSerializer, DoctorWriteSerializer


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
    lookup_field = 'username'
    lookup_value_regex = '[^/]+'
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
    permission_classes = [permissions.AllowAny]
    lookup_field = 'username'
    lookup_value_regex = '[^/]+'

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


class DoctorSignupView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = DoctorWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Create tokens
        refresh = RefreshToken.for_user(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'doctor': DoctorSerializer(user, context={'request': request}).data,
        }
        return Response(data, status=status.HTTP_201_CREATED)


class DoctorLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')
        if not username or not password:
            return Response({'detail': 'username/email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        # Allow login by username or email
        user = authenticate(request, username=username, password=password)
        if user is None:
            # try to authenticate by email
            try:
                u = User.objects.get(email=username)
            except User.DoesNotExist:
                return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            user = authenticate(request, username=u.username, password=password)
            if user is None:
                return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_doctor():
            return Response({'detail': 'User is not a doctor'}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'doctor': DoctorSerializer(user, context={'request': request}).data,
        }
        return Response(data)

class ImageSampleViewSet(viewsets.ModelViewSet):
    queryset = ImageSample.objects.select_related('content_type')
    permission_classes = [permissions.AllowAny]
    serializer_class = ImageSampleSerializer

    def perform_create(self, serializer):
        # Validator: max 5 images per checkup (check by content_type + object_id)
        ct = serializer.validated_data.get('content_type')
        object_id = serializer.validated_data.get('object_id')
        if ct and object_id:
            from django.contrib.contenttypes.models import ContentType
            # `ct` may be a ContentType instance or an app_label.model string handled in serializer
            if not isinstance(ct, ContentType):
                try:
                    app_label, model = str(ct).split('.')
                    ct = ContentType.objects.get(app_label=app_label, model=model)
                except Exception:
                    ct = None

            if ct is not None:
                existing = ImageSample.objects.filter(content_type=ct, object_id=object_id).count()
                if existing >= 5:
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
