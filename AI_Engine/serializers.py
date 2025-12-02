from rest_framework import serializers
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

    class Meta:
        model = ImageSample
        fields = [
            'id',
            'checkup',
            'image',
            'uploaded_at',
            'result',
        ]
        read_only_fields = ['uploaded_at', 'result']
