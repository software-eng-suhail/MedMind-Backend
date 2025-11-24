from rest_framework import serializers
from user.models import User
from user.models import DoctorProfile


class DoctorSerializer(serializers.ModelSerializer):
    credits = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'credits',
            'account_status',
            'created_at',
        ]

    def get_credits(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'credits', None) if profile else None

    def get_account_status(self, obj):
        profile = getattr(obj, 'doctor_profile', None)
        return getattr(profile, 'account_status', None) if profile else None


class DoctorWriteSerializer(serializers.ModelSerializer):
    # write serializer for creating/updating doctor users
    password = serializers.CharField(write_only=True, required=True)
    credits = serializers.IntegerField(write_only=True, required=False)
    account_status = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'credits', 'account_status']

    def create(self, validated_data):
        credits = validated_data.pop('credits', None)
        account_status = validated_data.pop('account_status', 'active')
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
        profile.save()
        return user

    def update(self, instance, validated_data):
        # allow updating username/email/password and profile fields
        password = validated_data.pop('password', None)
        credits = validated_data.pop('credits', None)
        account_status = validated_data.pop('account_status', None)

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
        profile.save()

        return instance
