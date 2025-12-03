from rest_framework import serializers
from django.db import transaction

from .models import Checkup, SkinCancerCheckup
from AI_Engine.models import ImageSample
from user.models import User


# Constants to avoid repetition
LESION_KEYS = {
	"lesion_size_mm",
	"lesion_location",
	"asymmetry",
	"border_irregularity",
	"color_variation",
	"diameter_mm",
	"evolution",
}

PARENT_FIELDS = ("age", "gender", "blood_type", "note", "status", "doctor", "created_at")


def _copy_parent_fields(target, source, fields):
	for f in fields:
		val = getattr(source, f, None)
		if val is not None:
			setattr(target, f, val)


class ImageSampleInlineSerializer(serializers.ModelSerializer):
	class Meta:
		model = ImageSample
		fields = ("id", "image", "uploaded_at")
		read_only_fields = ("uploaded_at",)


class SkinCancerCheckupSerializer(serializers.ModelSerializer):
	class Meta:
		model = SkinCancerCheckup
		fields = tuple(sorted(LESION_KEYS.union({"id"})))


class CheckupSerializer(serializers.ModelSerializer):
	image_samples = ImageSampleInlineSerializer(many=True, read_only=True)
	skin_cancer = SkinCancerCheckupSerializer(read_only=True, source="skincancercheckup")

	class Meta:
		model = Checkup
		fields = (
			"id",
			"age",
			"gender",
			"blood_type",
			"note",
			"status",
			"created_at",
			"doctor",
			"image_samples",
			"skin_cancer",
		)
		read_only_fields = ("created_at",)

	def validate(self, data):
		request = self.context.get("request")
		files = []
		if request is not None:
			files = request.FILES.getlist("images") if hasattr(request.FILES, "getlist") else []
		elif getattr(self, "initial_data", None):
			files = self.initial_data.get("image_samples", [])

		if files and len(files) > 5:
			raise serializers.ValidationError("A maximum of 5 images is allowed per checkup.")
		return data

	def create(self, validated_data):
		request = self.context.get("request")
		files = request.FILES.getlist("images") if request and hasattr(request.FILES, "getlist") else []

		checkup = Checkup.objects.create(**validated_data)

		if files:
			if len(files) > 5:
				raise serializers.ValidationError("A maximum of 5 images is allowed per checkup.")
			for f in files:
				ImageSample.objects.create(checkup=checkup, image=f)

		return checkup


class SkinCancerCreateSerializer(serializers.ModelSerializer):
	"""Create or attach a SkinCancerCheckup. Supports passing an existing
	`checkup` PK or providing inline base fields (age, gender, blood_type).
	"""

	checkup = serializers.PrimaryKeyRelatedField(queryset=Checkup.objects.all(), write_only=True, required=False)
	age = serializers.IntegerField(write_only=True, required=False)
	gender = serializers.CharField(write_only=True, required=False)
	blood_type = serializers.CharField(write_only=True, required=False)
	note = serializers.CharField(write_only=True, required=False, allow_blank=True)
	status = serializers.CharField(write_only=True, required=False)
	doctor = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True, required=False)

	class Meta:
		model = SkinCancerCheckup
		fields = ("id", "checkup",) + tuple(k for k in ("age", "gender", "blood_type", "note", "status", "doctor")) + tuple(sorted(LESION_KEYS))

	def validate(self, attrs):
		if not attrs.get("checkup"):
			missing = [f for f in ("age", "gender", "blood_type") if f not in attrs]
			if missing:
				raise serializers.ValidationError({"non_field_errors": f"Missing required base checkup fields: {', '.join(missing)}"})
		return attrs

	def create(self, validated_data):
		lesion_fields = {k: validated_data.pop(k) for k in list(validated_data.keys()) if k in LESION_KEYS}

		checkup_obj = validated_data.pop("checkup", None)

		if checkup_obj:
			if hasattr(checkup_obj, "skincancercheckup"):
				raise serializers.ValidationError({"checkup": "This checkup already has a SkinCancerCheckup."})

			child = SkinCancerCheckup(**lesion_fields)
			_copy_parent_fields(child, checkup_obj, PARENT_FIELDS)
			child.pk = checkup_obj.pk
			child.save()
			return child

		# Inline creation of parent + child
		checkup_fields = {f: validated_data.pop(f) for f in ("age", "gender", "blood_type", "note", "status") if f in validated_data}

		doctor_obj = validated_data.pop("doctor", None)
		request = self.context.get("request")
		if doctor_obj:
			checkup_fields["doctor"] = doctor_obj
		else:
			if request and getattr(request, "user", None) and request.user.is_authenticated:
				checkup_fields["doctor"] = request.user
			else:
				raise serializers.ValidationError({"doctor": "Provide doctor id or authenticate as a doctor"})

		with transaction.atomic():
			missing = [f for f in ("age", "gender", "blood_type") if f not in checkup_fields]
			if missing:
				raise serializers.ValidationError({"non_field_errors": f"Missing required base checkup fields: {', '.join(missing)}"})

			checkup = Checkup.objects.create(**checkup_fields)

			child = SkinCancerCheckup(**lesion_fields)
			_copy_parent_fields(child, checkup, PARENT_FIELDS)
			child.pk = checkup.pk
			child.save()
			return child
