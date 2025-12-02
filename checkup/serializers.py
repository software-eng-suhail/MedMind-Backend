# serializers for Checkup and SkinCancerCheckup
from rest_framework import serializers
from .models import Checkup, SkinCancerCheckup
from AI_Engine.models import ImageSample


class ImageSampleInlineSerializer(serializers.ModelSerializer):
	class Meta:
		model = ImageSample
		fields = ['id', 'image', 'uploaded_at']
		read_only_fields = ['uploaded_at']


class SkinCancerCheckupSerializer(serializers.ModelSerializer):
	# Allow clients to supply a checkup id when creating a SkinCancerCheckup
	checkup = serializers.PrimaryKeyRelatedField(queryset=Checkup.objects.all())

	class Meta:
		model = SkinCancerCheckup
		fields = [
			'id',
			'checkup',
			'lesion_size_mm',
			'lesion_location',
			'asymmetry',
			'border_irregularity',
			'color_variation',
			'diameter_mm',
			'evolution',
		]

	def validate_checkup(self, value):
		# Prevent creating a second SkinCancerCheckup for the same Checkup
		qs = SkinCancerCheckup.objects.filter(checkup=value)
		if self.instance is None:
			if qs.exists():
				raise serializers.ValidationError('This checkup already has a SkinCancerCheckup record.')
		else:
			# updating: allow if it's the same instance, but not if another exists
			if self.instance.checkup != value and qs.exists():
				raise serializers.ValidationError('This checkup already has a SkinCancerCheckup record.')
		return value


class CheckupSerializer(serializers.ModelSerializer):
	image_samples = ImageSampleInlineSerializer(many=True, read_only=True)
	skin_cancer = SkinCancerCheckupSerializer(read_only=True)

	class Meta:
		model = Checkup
		fields = [
			'id',
			'age',
			'gender',
			'blood_type',
			'note',
			'status',
			'created_at',
			'doctor',
			'image_samples',
			'skin_cancer',
		]
		read_only_fields = ['created_at']

	def validate(self, data):
		# If caller provides files in context (e.g., request.FILES['images']), enforce max 5
		request = self.context.get('request')
		files = []
		if request is not None:
			files = request.FILES.getlist('images') if hasattr(request.FILES, 'getlist') else []
		elif self.initial_data:
			# potential client-side nested payload
			files = self.initial_data.get('image_samples', [])

		if files and len(files) > 5:
			raise serializers.ValidationError('A maximum of 5 images is allowed per checkup.')
		return data

	def create(self, validated_data):
		# Support creating a checkup and attaching uploaded images from request.FILES['images']
		request = self.context.get('request')
		files = request.FILES.getlist('images') if request and hasattr(request.FILES, 'getlist') else []

		checkup = Checkup.objects.create(**validated_data)

		if files:
			if len(files) > 5:
				raise serializers.ValidationError('A maximum of 5 images is allowed per checkup.')
			for f in files:
				ImageSample.objects.create(checkup=checkup, image=f)

		return checkup
