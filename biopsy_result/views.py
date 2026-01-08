from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from biopsy_result.models import BiopsyResult, BiopsyResultStatus
from biopsy_result.serializers import BiopsyResultUploadSerializer, BiopsyResultReviewSerializer


class BiopsyResultViewSet(viewsets.ModelViewSet):
	queryset = BiopsyResult.objects.select_related('content_type', 'verified_by')
	permission_classes = [permissions.IsAuthenticated]

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return BiopsyResultUploadSerializer
		return BiopsyResultReviewSerializer

	@action(detail=True, methods=['post'], url_path='verify', permission_classes=[permissions.IsAdminUser])
	def verify(self, request, pk=None):
		"""Mark biopsy result as verified, set verifier, refund doctor credits atomically."""
		biopsy = self.get_object()
		admin_user = request.user
		# Defensive: ensure user is an admin per custom role
		if not getattr(admin_user, 'is_admin', lambda: False)():
			return Response({'detail': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

		with transaction.atomic():
			# Update biopsy status and verifier
			biopsy.status = BiopsyResultStatus.VERIFIED
			biopsy.verified_by = admin_user

			# Refund doctor credits once
			if not biopsy.credits_refunded:
				checkup = getattr(biopsy, 'checkup', None)
				doctor = getattr(checkup, 'doctor', None) if checkup else None
				profile = getattr(doctor, 'doctor_profile', None) if doctor else None
				if profile:
					profile.credits = (profile.credits) + 100
					profile.save(update_fields=['credits'])
				biopsy.credits_refunded = True

			biopsy.save(update_fields=['status', 'verified_by', 'credits_refunded'])

		serializer = self.get_serializer(biopsy)
		return Response(serializer.data, status=status.HTTP_200_OK)
