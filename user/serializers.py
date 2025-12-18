from rest_framework import serializers
from user.models import User
from user.models import DoctorProfile, DoctorAccountStatus


class DoctorSerializer(serializers.ModelSerializer):
    credits = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'name',
            'username',
            'email',
            'credits',
            'account_status',
            'profile_picture',
            'created_at',
        ]

    def get_credits(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'credits', None) if profile else None

    def get_account_status(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'account_status', None) if profile else None

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


class DoctorWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    credits = serializers.IntegerField(write_only=True, required=False)
    account_status = serializers.ChoiceField(choices=DoctorAccountStatus.choices, required=False)
    profile_picture = serializers.ImageField(write_only=False, required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'username', 'email', 'password', 'credits', 'account_status', 'profile_picture']

    def create(self, validated_data):
        credits = validated_data.pop('credits', None)
        account_status = validated_data.pop('account_status', DoctorAccountStatus.ACTIVE)
        profile_picture = validated_data.pop('profile_picture', None)
        password = validated_data.pop('password')
        # enforce doctor role
        validated_data['role'] = User.Role.DOCTOR
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        # ensure profile exists and set fields
        profile, _ = DoctorProfile.objects.get_or_create(user=user)
        if credits is not None:
            profile.credits = credits
        profile.account_status = account_status
        if profile_picture is not None:
            profile.profile_picture = profile_picture
        profile.save()
        return user

    def update(self, instance, validated_data):
        # allow updating username/email/password and profile fields
        password = validated_data.pop('password', None)
        credits = validated_data.pop('credits', None)
        account_status = validated_data.pop('account_status', None)
        profile_picture = validated_data.pop('profile_picture', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        profile, _ = DoctorProfile.objects.get_or_create(user=instance)
        if credits is not None:
            profile.credits = credits
        if account_status is not None:
            profile.account_status = account_status
        if profile_picture is not None:
            profile.profile_picture = profile_picture
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
