from __future__ import annotations

from django.db import models
from django.conf import settings


class CreditBundle(models.TextChoices):
    SMALL = "SMALL", "Small"
    MEDIUM = "MEDIUM", "Medium"
    LARGE = "LARGE", "Large"


BUNDLE_MAP = {
    CreditBundle.SMALL: {"credits": 5000, "amount_usd": 20},
    CreditBundle.MEDIUM: {"credits": 10000, "amount_usd": 35},
    CreditBundle.LARGE: {"credits": 20000, "amount_usd": 60},
}


class CreditTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_transactions")
    bundle = models.CharField(max_length=20, choices=CreditBundle.choices)
    credits_added = models.IntegerField()
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=50, default="SIMULATED")
    provider_ref = models.CharField(max_length=100, blank=True, null=True)
    idempotency_key = models.CharField(max_length=100)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "idempotency_key"], name="uniq_credit_txn_idem_per_doctor"),
        ]

    def __str__(self):
        return f"CreditTxn({self.pk}) {self.doctor_id} {self.bundle} {self.status}"
