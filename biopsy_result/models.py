from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from user.models import User

class BiopsyResultStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    VERIFIED = 'VERIFIED', 'Verified'
    REJECTED = 'REJECTED', 'Rejected'

class BiopsyResult(models.Model):
    # Generic relation to associate this biopsy result with any concrete checkup subtype
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    checkup = GenericForeignKey('content_type', 'object_id')

    result = models.TextField()
    document = models.FileField(upload_to='biopsy_results/')
    status = models.CharField(max_length=20, choices=BiopsyResultStatus.choices, default=BiopsyResultStatus.PENDING)
    credits_refunded = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biopsy_results')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id'], name='unique_biopsy_per_checkup')
        ]

    def __str__(self):
        return f"BiopsyResult({self.pk}) Status={self.status}"
    