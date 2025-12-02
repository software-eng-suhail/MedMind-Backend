from rest_framework import serializers
from .models import BiopsyResult


class BiopsyResultSerializer(serializers.ModelSerializer):
	class Meta:
		model = BiopsyResult
		fields = [
			'id',
			'checkup',
			'result',
			'image',
			'status',
			'credits_refunded',
			'verified_by',
			'uploaded_at',
		]
		read_only_fields = ['uploaded_at']
