import logging
from smtplib import SMTPException

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.generics import DestroyAPIView, ListCreateAPIView
from rest_framework.views import APIView

from .models import ConfirmEmailToken, Address
from .permissions import IsBuyer
from .serializers import (ConfirmEmailSerializer, RegistrationSerializer,
                          LoginSerializer, AddressSerializer)


logger = logging.getLogger(__name__)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                user = serializer.save()
                _, raw_token = ConfirmEmailToken.issue_for(user)

                send_mail(
                    subject="Подтверждение регистрации",
                    message=(
                        "Для подтверждения регистрации отправьте POST-запрос "
                        "на /api/accounts/confirm-email/ с JSON-полями "
                        f'email: "{user.email}" и token: "{raw_token}".'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
        except (SMTPException, OSError):
            logger.exception("Не удалось отправить письмо подтверждения.")
            return Response(
                {"detail": "Не удалось отправить письмо подтверждения."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"detail": "Регистрация создана. Проверьте почту."},
            status=status.HTTP_201_CREATED,
        )


class ConfirmEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        raw_token = serializer.validated_data["token"]
        confirmation = ConfirmEmailToken.find_valid(raw_token)

        if (
            confirmation is None
            or confirmation.user.email.casefold() != email.casefold()
        ):
            return Response(
                {"detail": "Токен недействителен или срок его действия истёк."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            confirmation = (
                ConfirmEmailToken.objects
                .select_for_update()
                .select_related("user")
                .filter(
                    pk=confirmation.pk,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )

            if confirmation is None:
                return Response(
                    {"detail": "Токен недействителен или срок его действия истёк."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = confirmation.user
            user.is_active = True
            user.save(update_fields=["is_active"])
            confirmation.delete()

        return Response(
            {"detail": "Email подтверждён."},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {"token": token.key},
            status=status.HTTP_200_OK,
        )


class AddressListCreateView(ListCreateAPIView):
    serializer_class = AddressSerializer
    permission_classes = [IsBuyer]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user).order_by("id")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDeleteView(DestroyAPIView):
    serializer_class = AddressSerializer
    permission_classes = [IsBuyer]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)
