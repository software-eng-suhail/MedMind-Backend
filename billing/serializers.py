from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from billing.models import BUNDLE_MAP, CreditBundle, CreditTransaction
from user.models import User


class CreditPurchaseSerializer(serializers.Serializer):
    bundle = serializers.ChoiceField(choices=CreditBundle.choices)
    idempotency_key = serializers.CharField(max_length=100)
    doctor_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user: User = getattr(request, "user", None)
        bundle = attrs.get("bundle")
        doctor_id = attrs.get("doctor_id")

        # Resolve target doctor based on role
        if getattr(user, "is_doctor", lambda: False)():
            attrs["doctor"] = user
        else:
            if doctor_id is None:
                raise serializers.ValidationError({"doctor_id": "This field is required for admins."})
            try:
                doctor = User.objects.get(pk=doctor_id, role=User.Role.DOCTOR)
            except User.DoesNotExist:
                raise serializers.ValidationError({"doctor_id": "Doctor not found."})
            attrs["doctor"] = doctor

        # Bundle mapping sanity check
        if bundle not in BUNDLE_MAP:
            raise serializers.ValidationError({"bundle": "Invalid bundle."})

        # Ensure idempotency key uniqueness per doctor
        existing = CreditTransaction.objects.filter(
            doctor=attrs["doctor"], idempotency_key=attrs["idempotency_key"], status=CreditTransaction.Status.SUCCESS
        ).first()
        attrs["existing_txn"] = existing
        return attrs

    def create(self, validated_data):
        doctor = validated_data["doctor"]
        bundle = validated_data["bundle"]
        idem_key = validated_data["idempotency_key"]
        existing = validated_data.pop("existing_txn", None)

        # Idempotent return
        if existing:
            profile = getattr(doctor, "doctor_profile", None)
            return existing, getattr(profile, "credits", None)

        bundle_info = BUNDLE_MAP[bundle]
        credits = bundle_info["credits"]
        amount_usd = bundle_info["amount_usd"]

        with transaction.atomic():
            txn = CreditTransaction.objects.create(
                doctor=doctor,
                bundle=bundle,
                credits_added=credits,
                amount_usd=amount_usd,
                idempotency_key=idem_key,
                status=CreditTransaction.Status.PENDING,
            )

            profile = getattr(doctor, "doctor_profile", None)
            if profile is None:
                raise serializers.ValidationError({"doctor": "Doctor profile missing."})
            profile.credits = profile.credits + credits
            profile.save(update_fields=["credits"])

            txn.status = CreditTransaction.Status.SUCCESS
            txn.save(update_fields=["status"])

        return txn, profile.credits


class CreditTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTransaction
        fields = [
            "id",
            "doctor",
            "bundle",
            "credits_added",
            "amount_usd",
            "status",
            "provider",
            "provider_ref",
            "idempotency_key",
            "created_at",
        ]
        read_only_fields = fields
