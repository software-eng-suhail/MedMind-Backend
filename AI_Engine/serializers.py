from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import ImageSample, ImageResult


class ImageResultReadSerializer(serializers.ModelSerializer):
    xai_image = serializers.ImageField(read_only=True)

    class Meta:
        model = ImageResult
        fields = [
            'id',
            'result',
            'model',
            'confidence',
            'xai_image',
        ]


class ImageResultWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageResult
        fields = [
            'id',
            'image_sample',
            'result',
            'model',
            'confidence',
            'xai_image',
        ]


class ImageSampleSerializer(serializers.ModelSerializer):
    result = ImageResultReadSerializer(many=True, read_only=True)
    image = serializers.ImageField()
    # For write: accept `content_type` as app_label.model string and `object_id`.
    content_type = serializers.CharField(write_only=True, required=False)
    object_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ImageSample
        fields = [
            'id',
            'content_type',
            'object_id',
            'image',
            'uploaded_at',
            'result',
        ]
        read_only_fields = ['uploaded_at', 'result']

    def create(self, validated_data):
        # Map content_type string to ContentType
        ct_label = validated_data.pop('content_type', None)
        object_id = validated_data.pop('object_id', None)
        if ct_label and object_id:
            try:
                app_label, model = ct_label.split('.')
                ct = ContentType.objects.get(app_label=app_label, model=model)
            except Exception:
                raise serializers.ValidationError({'content_type': 'Invalid content_type. Use "app_label.model" format.'})
            validated_data['content_type'] = ct
            validated_data['object_id'] = object_id

        return super().create(validated_data)
