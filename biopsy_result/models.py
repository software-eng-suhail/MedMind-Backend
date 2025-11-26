from django.db import models
from user.models import User
from checkup.models import Checkup

class BiopsyResultStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    VERIFIED = 'VERIFIED', 'Verified'
    REJECTED = 'REJECTED', 'Rejected'

class BiopsyResult(models.Model):
    checkup = models.OneToOneField(Checkup, on_delete=models.CASCADE, related_name='biopsy_results')
    result = models.TextField()
    image = models.ImageField(upload_to='biopsy_results/')
    status = models.CharField(max_length=20, choices=BiopsyResultStatus.choices, default=BiopsyResultStatus.PENDING)
    credits_refunded = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biopsy_results')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"BiopsyResult({self.pk}) Status={self.status}"
    