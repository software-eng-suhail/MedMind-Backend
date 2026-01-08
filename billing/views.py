from __future__ import annotations

from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from billing.models import CreditTransaction
from billing.serializers import CreditPurchaseSerializer, CreditTransactionSerializer


class BillingViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def create(self, request):
        serializer = CreditPurchaseSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        txn, balance = serializer.save()
        txn_data = CreditTransactionSerializer(txn).data
        txn_data["new_balance"] = balance
        return Response(txn_data, status=status.HTTP_201_CREATED)

    def list(self, request):
        user = request.user
        qs = CreditTransaction.objects.all()
        if getattr(user, "is_doctor", lambda: False)():
            qs = qs.filter(doctor=user)
        serializer = CreditTransactionSerializer(qs.order_by("-created_at"), many=True)
        return Response(serializer.data)
