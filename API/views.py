from rest_framework import permissions, viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from user.serializers import DoctorSerializer, DoctorWriteSerializer, AdminSerializer, AdminWriteSerializer
from user.models import User

# app imports
from AI_Engine.models import ImageSample, ImageResult
from AI_Engine.serializers import ImageSampleSerializer, ImageResultReadSerializer, ImageResultWriteSerializer
from biopsy_result.models import BiopsyResult
from biopsy_result.serializers import BiopsyResultSerializer
from checkup.models import Checkup, SkinCancerCheckup
from checkup.serializers import (
    CheckupSerializer,
    SkinCancerCheckupSerializer,
    SkinCancerCreateSerializer,
)


class DoctorViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
    permission_classes = [permissions.AllowAny]

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

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def public_list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = DoctorSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = DoctorSerializer(qs, many=True)
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


class CheckupViewSet(viewsets.ModelViewSet):
    # Select the doctor and the subclass row (if any) and prefetch images
    queryset = Checkup.objects.select_related('doctor', 'skincancercheckup').prefetch_related('image_samples')
    permission_classes = [permissions.AllowAny]
    serializer_class = CheckupSerializer

    def create(self, request, *args, **kwargs):
        # Prevent creating bare Checkup instances; require subtype endpoints
        raise serializers.ValidationError(
            "Create checkups via subtype endpoints (for example POST /skin-cancer/)."
        )


class SkinCancerCheckupViewSet(viewsets.ModelViewSet):
    queryset = SkinCancerCheckup.objects.all()
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.action == 'create':
            return SkinCancerCreateSerializer
        return SkinCancerCheckupSerializer

    def create(self, request, *args, **kwargs):
        # Delegate creation to serializer which handles creating base Checkup and child row
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # Return the full Checkup representation (includes nested skincancer data)
        parent = Checkup.objects.get(pk=instance.pk)
        out = CheckupSerializer(parent, context=self.get_serializer_context()).data
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)


class ImageSampleViewSet(viewsets.ModelViewSet):
    queryset = ImageSample.objects.select_related('checkup')
    permission_classes = [permissions.AllowAny]
    serializer_class = ImageSampleSerializer

    def perform_create(self, serializer):
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
