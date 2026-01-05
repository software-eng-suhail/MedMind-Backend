from django.db import models
from django.contrib.contenttypes.fields import GenericRelation

class CheckupStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'


class CheckupType(models.TextChoices):
    SKIN_CANCER = 'SKIN_CANCER', 'Skin Cancer'
    MRI_ALZHEIMER = 'MRI_ALZHEIMER', 'MRI Alzheimer'
    DIABETES_RETINOPATHY = 'DIABETES_RETINOPATHY', 'Diabetes Retinopathy'


class Checkup(models.Model):
    age = models.IntegerField()
    gender = models.CharField(max_length=10)
    blood_type = models.CharField(max_length=3)
    note = models.TextField(blank=True, null=True)
    checkup_type = models.CharField(max_length=50, choices=CheckupType.choices, default=CheckupType.SKIN_CANCER)
    status = models.CharField(max_length=20, choices=CheckupStatus.choices, default=CheckupStatus.PENDING)
    task_id = models.CharField(max_length=255, blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    result = models.CharField(max_length=100, blank=True, null=True)
    final_confidence = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    doctor = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='checkups')
    image_count = models.IntegerField(default=0)

    class Meta:
        abstract = True

    def __str__(self):
        return f"Checkup({getattr(self, 'pk', None)}) Status={self.status}"

class SkinCancerCheckup(Checkup):
    lesion_size_mm = models.FloatField()
    lesion_location = models.CharField(max_length=100)
    asymmetry = models.BooleanField()
    border_irregularity = models.BooleanField()
    color_variation = models.BooleanField()
    diameter_mm = models.FloatField()
    evolution = models.BooleanField()
    image_samples = GenericRelation('AI_Engine.ImageSample', related_query_name='checkup')

    def __str__(self):
        return f"SkinCancerCheckup({self.pk})"