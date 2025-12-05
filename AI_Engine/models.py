from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings

class AIModel(models.TextChoices):
    MODEL_A = 'Model_A', 'AI Model A'
    MODEL_B = 'Model_B', 'AI Model B'
    MODEL_C = 'Model_C', 'AI Model C'


class ImageSample(models.Model):
    # Generic relation to allow attaching samples to any concrete checkup subtype
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    image = models.ImageField(upload_to='images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ImageSample({self.pk}) for {self.content_type}#{self.object_id}"

class ImageResult(models.Model):
    image_sample = models.ForeignKey(ImageSample, on_delete=models.CASCADE, related_name='result')
    result = models.TextField()
    model = models.CharField(max_length=100, choices=AIModel.choices)
    confidence = models.FloatField()
    xai_image = models.ImageField(upload_to='xai_images/')
    
    def __str__(self):
        return f"ImageResult({self.pk}) {self.model} conf={self.confidence}"