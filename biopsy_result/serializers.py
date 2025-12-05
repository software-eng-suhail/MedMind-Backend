from rest_framework import serializers
from .models import BiopsyResult


class BiopsyResultSerializer(serializers.ModelSerializer):
	# On write we accept content_type (app_label.model) + object_id to locate the checkup
	content_type = serializers.CharField(write_only=True, required=False)
	object_id = serializers.IntegerField(write_only=True, required=False)

	class Meta:
		model = BiopsyResult
		fields = [
			'id',
			'content_type',
			'object_id',
			'result',
			'document',
			'status',
			'credits_refunded',
			'verified_by',
			'uploaded_at',
		]
		read_only_fields = ['uploaded_at']

	def create(self, validated_data):
		ct_label = validated_data.pop('content_type', None)
		object_id = validated_data.pop('object_id', None)
		if ct_label and object_id:
			from django.contrib.contenttypes.models import ContentType
			try:
				app_label, model = ct_label.split('.')
				ct = ContentType.objects.get(app_label=app_label, model=model)
			except Exception:
				raise serializers.ValidationError({'content_type': 'Invalid content_type. Use "app_label.model" format.'})
			validated_data['content_type'] = ct
			validated_data['object_id'] = object_id
		return super().create(validated_data)
