from rest_framework import serializers
from .models import BiopsyResult


class BiopsyResultUploadSerializer(serializers.ModelSerializer):
	# Accept content_type (app_label.model) + object_id to locate the checkup
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


class BiopsyResultReviewSerializer(serializers.ModelSerializer):
	checkup = serializers.SerializerMethodField()
	doctor = serializers.SerializerMethodField()
	verified_by = serializers.SerializerMethodField()

	class Meta:
		model = BiopsyResult
		fields = [
			'id',
			'result',
			'document',
			'status',
			'credits_refunded',
			'verified_by',
			'uploaded_at',
			'checkup',
			'doctor',
		]
		read_only_fields = fields

	def _absolute_url(self, request, field):
		if not field:
			return None
		try:
			url = field.url
			if request is not None:
				return request.build_absolute_uri(url)
			return url
		except Exception:
			return None

	def get_checkup(self, obj):
		checkup = getattr(obj, 'checkup', None)
		from checkup.models import SkinCancerCheckup
		if not isinstance(checkup, SkinCancerCheckup):
			return None
		request = self.context.get('request') if hasattr(self, 'context') else None
		samples = getattr(checkup, 'image_samples', None)
		images = []
		if samples is not None:
			for s in samples.all():
				images.append(self._absolute_url(request, getattr(s, 'image', None)))

		return {
			'id': checkup.id,
			'age': checkup.age,
			'gender': checkup.gender,
			'blood_type': checkup.blood_type,
			'note': checkup.note,
			'checkup_type': getattr(checkup, 'checkup_type', None),
			'lesion_size_mm': getattr(checkup, 'lesion_size_mm', None),
			'lesion_location': getattr(checkup, 'lesion_location', None),
			'asymmetry': getattr(checkup, 'asymmetry', None),
			'border_irregularity': getattr(checkup, 'border_irregularity', None),
			'color_variation': getattr(checkup, 'color_variation', None),
			'diameter_mm': getattr(checkup, 'diameter_mm', None),
			'evolution': getattr(checkup, 'evolution', None),
			'images': [img for img in images if img],
		}

	def get_doctor(self, obj):
		checkup = getattr(obj, 'checkup', None)
		doctor = getattr(checkup, 'doctor', None) if checkup else None
		if not doctor:
			return None
		request = self.context.get('request') if hasattr(self, 'context') else None
		profile = getattr(doctor, 'doctor_profile', None)
		profile_pic = getattr(profile, 'profile_picture', None) if profile else None
		return {
			'id': doctor.id,
			'username': doctor.username,
			'name': getattr(doctor, 'name', None),
			'profile_picture': self._absolute_url(request, profile_pic),
		}

	def get_verified_by(self, obj):
		admin_user = getattr(obj, 'verified_by', None)
		if not admin_user:
			return None
		return {
			'id': admin_user.id,
			'name': getattr(admin_user, 'name', None),
		}
