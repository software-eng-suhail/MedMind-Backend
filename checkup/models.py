from django.db import models

class CheckupStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'


class Checkup(models.Model):
    age = models.IntegerField()
    gender = models.CharField(max_length=10)
    blood_type = models.CharField(max_length=3)
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=CheckupStatus.choices, default=CheckupStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    doctor = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='checkups')

    def __str__(self):
        return f"Checkup({self.pk}) Status={self.status}"

class SkinCancerCheckup(Checkup):
    # Use multi-table inheritance: SkinCancerCheckup is a Checkup subtype
    lesion_size_mm = models.FloatField()
    lesion_location = models.CharField(max_length=100)
    asymmetry = models.BooleanField()
    border_irregularity = models.BooleanField()
    color_variation = models.BooleanField()
    diameter_mm = models.FloatField()
    evolution = models.BooleanField()

    def __str__(self):
        return f"SkinCancerCheckup({self.pk})"