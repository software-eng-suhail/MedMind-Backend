from dataclasses import fields
from rest_framework import serializers
from user.models import User
from user.models import DoctorProfile, DoctorAccountStatus


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get('username') and not attrs.get('email'):
            raise serializers.ValidationError('Provide either username or email.')
        return attrs


class DoctorSerializer(serializers.ModelSerializer):
    credits = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()
    email_verification_status = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    license_image = serializers.SerializerMethodField()
    specialization = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'name',
            'username',
            'email',
            'credits',
            'account_status',
            'email_verification_status',
            'profile_picture',
            'license_image',
            'specialization',
            'created_at',
        ]
    read_only_fields = fields

    def get_credits(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'credits', None) if profile else None

    def get_account_status(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'account_status', None) if profile else None

    def get_email_verification_status(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'email_verification_status', None) if profile else None

    def get_profile_picture(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        pic = getattr(profile, 'profile_picture', None) if profile else None
        if not pic:
            return None
        request = self.context.get('request') if hasattr(self, 'context') else None
        try:
            url = pic.url
            if request is not None:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    def get_license_image(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        img = getattr(profile, 'license_image', None) if profile else None
        if not img:
            return None
        request = self.context.get('request') if hasattr(self, 'context') else None
        try:
            url = img.url
            if request is not None:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    def get_specialization(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'specialization', None) if profile else None


class DoctorWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    profile_picture = serializers.ImageField(source='doctor_profile.profile_picture', required=False, allow_null=True)
    license_image = serializers.ImageField(source='doctor_profile.license_image', required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True)
    specialization = serializers.CharField(source='doctor_profile.specialization', required=False)
    profile_picture_clear = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = User
        fields = ['id', 'name', 'username', 'email', 'password', 'profile_picture', 'license_image', 'specialization', 'profile_picture_clear']

    def validate(self, attrs):
        # Require these fields on create, but allow partial updates without them.
        if self.instance is None:
            password = attrs.get('password')
            doctor_profile = attrs.get('doctor_profile') or {}
            specialization = doctor_profile.get('specialization')
            if not password:
                raise serializers.ValidationError({'password': 'This field is required.'})
            if not specialization:
                raise serializers.ValidationError({'specialization': 'This field is required.'})
        return attrs

    def create(self, validated_data):
        profile_picture_clear = validated_data.pop('profile_picture_clear', False)
        doctor_profile_data = validated_data.pop('doctor_profile', {}) or {}
        profile_picture = doctor_profile_data.get('profile_picture', None)
        license_image = doctor_profile_data.get('license_image', None)
        specialization = doctor_profile_data.get('specialization', None)
        password = validated_data.pop('password', None)
        
        validated_data['role'] = User.Role.DOCTOR
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        
        profile, _ = DoctorProfile.objects.get_or_create(user=user)
        if profile_picture_clear:
            profile.profile_picture = None
        if profile_picture is not None:
            profile.profile_picture = profile_picture
        if license_image is not None:
            profile.license_image = license_image
        if specialization is not None:
            profile.specialization = specialization
        profile.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        profile_picture_clear = validated_data.pop('profile_picture_clear', False)
        doctor_profile_data = validated_data.pop('doctor_profile', {}) or {}
        profile_picture = doctor_profile_data.get('profile_picture', None)
        specialization = doctor_profile_data.get('specialization', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        profile, _ = DoctorProfile.objects.get_or_create(user=instance)
        if profile_picture_clear:
            profile.profile_picture = None
        if 'profile_picture' in doctor_profile_data:
            profile.profile_picture = profile_picture
        if specialization is not None:
            profile.specialization = specialization
        profile.save()

        return instance


class AdminSerializer(serializers.ModelSerializer):
    profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'name',
            'username',
            'email',
            'profile_id',
            'created_at',
        ]

    def get_profile_id(self, obj):
        profile = getattr(obj, 'admin_profile', None)
        return getattr(profile, 'pk', None) if profile else None


class AdminWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'username', 'email', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data['role'] = User.Role.ADMIN
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        # ensure admin profile exists
        from user.models import AdminProfile
        AdminProfile.objects.get_or_create(user=user)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        from user.models import AdminProfile
        AdminProfile.objects.get_or_create(user=instance)
        return instance
