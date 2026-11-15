import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("У пользователя должен быть email")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields["is_staff"] is not True:
            raise ValueError("У суперпользователя is_staff должен быть True")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("У суперпользователя is_superuser должен быть True")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        BUYER = "buyer", "Покупатель"
        SUPPLIER = "supplier", "Поставщик"

    username = None
    email = models.EmailField(unique=True, verbose_name="Email")
    middle_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Отчество",
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.BUYER,
        verbose_name="Роль",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Активен",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class ConfirmEmailToken(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_confirmation_token",
        verbose_name="Пользователь",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name="Хеш токена",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        verbose_name="Создан",
    )
    expires_at = models.DateTimeField(verbose_name="Истекает")

    class Meta:
        verbose_name = "Токен подтверждения email"
        verbose_name_plural = "Токены подтверждения email"

    def __str__(self):
        return f"Токен подтверждения для {self.user.email}"

    @classmethod
    def issue_for(cls, user):
        raw_token = secrets.token_urlsafe(32)
        now = timezone.now()

        token, _ = cls.objects.update_or_create(
            user=user,
            defaults={
                "token_hash": hashlib.sha256(
                    raw_token.encode('utf-8')
                ).hexdigest(),
                "created_at": now,
                "expires_at": now + timedelta(hours=24)
            },
        )
        return token, raw_token

    @classmethod
    def find_valid(cls, raw_token):
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        return ((cls.objects.select_related("user")
                .filter(token_hash=token_hash, expires_at__gt=timezone.now()))
                .first())


class Address(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="Пользователь",
    )
    city = models.CharField(
        max_length=100,
        verbose_name="Город"
    )
    street = models.CharField(
        max_length=150,
        verbose_name="Улица"
    )
    house = models.CharField(
        max_length=20,
        verbose_name="Дом"
    )
    structure = models.CharField(
        max_length=15,
        blank=True,
        verbose_name="Корпус"
    )
    building = models.CharField(
        max_length=15,
        blank=True,
        verbose_name="Строение"
    )
    apartment = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Квартира"
    )
    phone = models.CharField(
        max_length=30,
        verbose_name="Телефон"
    )

    class Meta:
        verbose_name = "Адрес доставки"
        verbose_name_plural = "Адреса доставки"

    def __str__(self):
        return f"{self.city}, {self.street}, {self.house}"
