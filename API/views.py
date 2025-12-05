from rest_framework import permissions, viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction

from user.serializers import DoctorSerializer, DoctorWriteSerializer, AdminSerializer, AdminWriteSerializer
from user.models import User

# app imports
from AI_Engine.models import ImageSample, ImageResult
from AI_Engine.serializers import ImageSampleSerializer, ImageResultReadSerializer, ImageResultWriteSerializer
from biopsy_result.models import BiopsyResult
from biopsy_result.serializers import BiopsyResultSerializer
from checkup.models import SkinCancerCheckup
from checkup.serializers import (
    SkinCancerCheckupSerializer,
    SkinCancerCreateSerializer,
)



class DoctorViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
    permission_classes = [permissions.AllowAny]
    lookup_field = 'username'
    # allow usernames with dots or other common characters
    lookup_value_regex = '[^/]+'

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
            return SkinCancerCreateSerializer
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
                from django.contrib.contenttypes.models import ContentType
                ct = ContentType.objects.get_for_model(instance)
                for f in files:
                    ImageSample.objects.create(content_type=ct, object_id=instance.pk, image=f)

        out = SkinCancerCheckupSerializer(instance, context=self.get_serializer_context()).data
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)


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
