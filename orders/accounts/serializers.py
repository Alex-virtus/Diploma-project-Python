from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password as django_validate_password
from rest_framework import serializers


User = get_user_model()


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    middle_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "middle_name",
            "email",
            "password",
        )

    def validate_password(self, value):
        django_validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(
            password=password,
            role=User.Role.BUYER,
            is_active=False,
            **validated_data,
        )


class ConfirmEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField()
