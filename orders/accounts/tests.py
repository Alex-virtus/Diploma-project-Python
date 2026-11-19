import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from .models import ConfirmEmailToken, Address


User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class RegistrationAndConfirmationTests(APITestCase):
    def setUp(self):
        self.email = "buyer@example.com"
        self.password = "Violet!River-7429-Clock"

    def register(self, **extra_data):
        data = {
            "first_name": "Test",
            "last_name": "Buyer",
            "email": self.email,
            "password": self.password,
            **extra_data,
        }
        return self.client.post(
            reverse("register"),
            data,
            format="json",
        )

    def test_registration_creates_inactive_buyer_and_sends_email(self):
        response = self.register(role="supplier")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=self.email)
        self.assertFalse(user.is_active)
        self.assertEqual(user.role, User.Role.BUYER)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            ConfirmEmailToken.objects.filter(user=user).exists()
        )

    def test_confirmation_activates_user_and_consumes_token(self):
        self.register()

        match = re.search(r'token: "([^"]+)"', mail.outbox[0].body)
        self.assertIsNotNone(match)
        token = match.group(1)

        response = self.client.post(
            reverse("confirm-email"),
            {"email": self.email, "token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email=self.email)
        self.assertTrue(user.is_active)
        self.assertFalse(
            ConfirmEmailToken.objects.filter(user=user).exists()
        )

    def test_invalid_confirmation_token_does_not_activate_user(self):
        self.register()

        response = self.client.post(
            reverse("confirm-email"),
            {"email": self.email, "token": "invalid-token"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(User.objects.get(email=self.email).is_active)

    def create_user(self, is_active=True):
        return User.objects.create_user(
            email=self.email,
            password=self.password,
            is_active=is_active,
        )

    def test_login_returns_token_for_active_user(self):
        user = self.create_user()

        response = self.client.post(
            reverse("login"),
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["token"],
            Token.objects.get(user=user).key,
        )

    def test_login_rejects_wrong_password(self):
        user = self.create_user()

        response = self.client.post(
            reverse("login"),
            {"email": self.email, "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_login_rejects_inactive_user(self):
        user = self.create_user(is_active=False)

        response = self.client.post(
            reverse("login"),
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertFalse(Token.objects.filter(user=user).exists())


class AddressAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            email="address-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.other_buyer = User.objects.create_user(
            email="other-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.supplier = User.objects.create_user(
            email="address-supplier@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )

        cls.buyer_token = Token.objects.create(user=cls.buyer)
        cls.supplier_token = Token.objects.create(user=cls.supplier)

        cls.buyer_address = Address.objects.create(
            user=cls.buyer,
            city="Москва",
            street="Ленина",
            house="10",
            phone="+79990000001",
        )
        cls.other_address = Address.objects.create(
            user=cls.other_buyer,
            city="Казань",
            street="Пушкина",
            house="5",
            phone="+79990000002",
        )

    def authenticate(self, token):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def test_buyer_lists_only_own_addresses(self):
        self.authenticate(self.buyer_token)

        response = self.client.get(reverse("address-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.buyer_address.id)

    def test_buyer_creates_address_for_self(self):
        self.authenticate(self.buyer_token)

        response = self.client.post(
            reverse("address-list"),
            {
                "city": "Самара",
                "street": "Мира",
                "house": "7",
                "phone": "+79990000003",
                "user": self.other_buyer.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = Address.objects.get(pk=response.data["id"])
        self.assertEqual(address.user, self.buyer)
        self.assertEqual(address.city, "Самара")

    def test_buyer_deletes_own_address(self):
        self.authenticate(self.buyer_token)

        response = self.client.delete(
            reverse(
                "address-delete",
                kwargs={"pk": self.buyer_address.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Address.objects.filter(pk=self.buyer_address.id).exists()
        )

    def test_buyer_cannot_delete_another_users_address(self):
        self.authenticate(self.buyer_token)

        response = self.client.delete(
            reverse(
                "address-delete",
                kwargs={"pk": self.other_address.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            Address.objects.filter(pk=self.other_address.id).exists()
        )

    def test_supplier_cannot_access_addresses(self):
        self.authenticate(self.supplier_token)

        response = self.client.get(reverse("address-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_access_addresses(self):
        response = self.client.get(reverse("address-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
