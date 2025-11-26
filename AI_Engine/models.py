from django.db import models
from checkup.models import Checkup

class AIModel(models.TextChoices):
    MODEL_A = 'Model_A', 'AI Model A'
    MODEL_B = 'Model_B', 'AI Model B'
    MODEL_C = 'Model_C', 'AI Model C'


class ImageSample(models.Model):
    checkup = models.ForeignKey(Checkup, on_delete=models.CASCADE, related_name='image_samples')
    image = models.ImageField(upload_to='images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ImageSample({self.pk})"

class ImageResult(models.Model):
    image_sample = models.ForeignKey(ImageSample, on_delete=models.CASCADE, related_name='result')
    result = models.TextField()
    model = models.CharField(max_length=100, choices=AIModel.choices)
    confidence = models.FloatField()
    xai_image = models.ImageField(upload_to='xai_images/')
    
    def __str__(self):
        return f"ImageResult({self.pk}) {self.model} conf={self.confidence}"