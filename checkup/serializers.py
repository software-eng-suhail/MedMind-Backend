from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import SkinCancerCheckup
from AI_Engine.models import ImageSample
from AI_Engine.serializers import ImageSampleSerializer
from user.serializers import DoctorSerializer
from user.models import User


class SkinCancerCheckupSerializer(serializers.ModelSerializer):
    doctor = DoctorSerializer(read_only=True)
    image_samples = ImageSampleSerializer(many=True, read_only=True)

    class Meta:
        model = SkinCancerCheckup
        fields = [
            'id',
            'age',
            'gender',
            'blood_type',
            'note',
            'checkup_type',
            'status',
            'task_id',
            'started_at',
            'completed_at',
            'created_at',
            'doctor',
            'lesion_size_mm',
            'lesion_location',
            'asymmetry',
            'border_irregularity',
            'color_variation',
            'diameter_mm',
            'evolution',
            'image_samples',
            'image_count',
            'result',
            'final_confidence',
        ]
        read_only_fields = ['id', 'created_at', 'image_samples', 'checkup_type', 'image_count', 'result', 'final_confidence']


class SkinCancerCheckupCreateSerializer(serializers.ModelSerializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.DOCTOR))
    class ImageUploadSerializer(serializers.Serializer):
        image = serializers.ImageField()

    images = ImageUploadSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = SkinCancerCheckup
        fields = [
            'id',
            'age',
            'gender',
            'blood_type',
            'note',
            'checkup_type',
            'doctor',
            'lesion_size_mm',
            'lesion_location',
            'asymmetry',
            'border_irregularity',
            'color_variation',
            'diameter_mm',
            'evolution',
            'images',
        ]
        read_only_fields = ['id', 'checkup_type']

    def to_representation(self, instance):
        return SkinCancerCheckupSerializer(instance, context=self.context).data

    def validate(self, data):
        images = data.get('images') or []
        if len(images) > 5:
            raise serializers.ValidationError({'images': 'A maximum of 5 images is allowed.'})
        return data

    def create(self, validated_data):
        images = validated_data.pop('images', [])
        with transaction.atomic():
            instance = super().create(validated_data)

            if images:
                ct = ContentType.objects.get_for_model(instance)
                for img in images:
                    image_file = img.get('image') if isinstance(img, dict) else img
                    ImageSample.objects.create(content_type=ct, object_id=instance.pk, image=image_file)
            
            instance.image_count = len(images)
            instance.save(update_fields=['image_count'])

        return instance


class SkinCancerCheckupListSerializer(serializers.ModelSerializer):

    class Meta:
        model = SkinCancerCheckup
        fields = [
            'id',
            'age',
            'gender',
            'created_at',
            'result',
            'final_confidence',
            'checkup_type',
            'image_count',
        ]
        read_only_fields = fields
