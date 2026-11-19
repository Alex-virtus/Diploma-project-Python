from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Category, Product, ProductInfo, Shop


User = get_user_model()


class ProductListAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        supplier_one = User.objects.create_user(
            email="supplier1@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )
        supplier_two = User.objects.create_user(
            email="supplier2@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )

        cls.shop_one = Shop.objects.create(
            name="Alpha Store",
            user=supplier_one,
        )
        cls.shop_two = Shop.objects.create(
            name="Beta Store",
            user=supplier_two,
        )

        cls.phones = Category.objects.create(name="Phones")
        cls.storage = Category.objects.create(name="Storage")

        galaxy = Product.objects.create(
            category=cls.phones,
            name="Galaxy S",
            description="Large screen smartphone",
        )
        iphone = Product.objects.create(
            category=cls.phones,
            name="iPhone",
            description="Compact smartphone",
        )
        flash_drive = Product.objects.create(
            category=cls.storage,
            name="USB Drive",
            description="Portable flash drive",
        )

        cls.galaxy_offer = cls.create_offer(
            shop=cls.shop_one,
            product=galaxy,
            external_id=101,
        )
        cls.iphone_offer = cls.create_offer(
            shop=cls.shop_two,
            product=iphone,
            external_id=102,
        )
        cls.flash_drive_offer = cls.create_offer(
            shop=cls.shop_one,
            product=flash_drive,
            external_id=103,
        )

    @classmethod
    def create_offer(cls, shop, product, external_id):
        return ProductInfo.objects.create(
            shop=shop,
            product=product,
            external_id=external_id,
            quantity=5,
            price=Decimal("10.00"),
            price_rrc=Decimal("12.00"),
        )

    def test_lists_products_with_expected_fields(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(
            set(response.data[0]),
            {
                "id",
                "name",
                "description",
                "supplier",
                "category",
                "parameters",
                "price",
                "price_rrc",
                "quantity",
            },
        )

    def test_search_matches_product_description_case_insensitively(self):
        response = self.client.get(
            reverse("product-list"),
            {"search": "PORTABLE"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [self.flash_drive_offer.id],
        )

    def test_filters_by_category(self):
        response = self.client.get(
            reverse("product-list"),
            {"category_id": self.phones.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data},
            {self.galaxy_offer.id, self.iphone_offer.id},
        )

    def test_filters_by_shop(self):
        response = self.client.get(
            reverse("product-list"),
            {"shop_id": self.shop_one.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data},
            {self.galaxy_offer.id, self.flash_drive_offer.id},
        )

    def test_search_and_filters_can_be_combined(self):
        response = self.client.get(
            reverse("product-list"),
            {
                "search": "galaxy",
                "category_id": self.phones.id,
                "shop_id": self.shop_one.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [self.galaxy_offer.id],
        )

    def test_rejects_invalid_filter_id(self):
        response = self.client.get(
            reverse("product-list"),
            {"category_id": "not-an-id"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class PriceImportAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = User.objects.create_user(
            email="import-supplier@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )
        cls.buyer = User.objects.create_user(
            email="import-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.supplier_token = Token.objects.create(user=cls.supplier)
        cls.buyer_token = Token.objects.create(user=cls.buyer)

    def upload(self, content):
        return SimpleUploadedFile(
            "price.yaml",
            content.encode("utf-8"),
            content_type="application/x-yaml",
        )

    def test_supplier_can_import_yaml_price(self):
        yaml_content = """
shop: Test Supplier Shop
categories:
  - id: 1
    name: Test Category
goods:
  - id: 1001
    category: 1
    name: Test Product
    price: 10.50
    price_rrc: 12.00
    quantity: 7
    parameters:
      Color: blue
"""

        response = self.client.post(
            reverse("price-import"),
            {"file": self.upload(yaml_content)},
            HTTP_AUTHORIZATION=f"Token {self.supplier_token.key}",
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["imported"], 1)
        self.assertTrue(
            ProductInfo.objects.filter(
                shop__user=self.supplier,
                external_id=1001,
                quantity=7,
            ).exists()
        )

    def test_buyer_cannot_import_yaml_price(self):
        response = self.client.post(
            reverse("price-import"),
            {"file": self.upload("shop: Test")},
            HTTP_AUTHORIZATION=f"Token {self.buyer_token.key}",
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ProductInfo.objects.count(), 0)

    def test_anonymous_user_cannot_import_yaml_price(self):
        response = self.client.post(
            reverse("price-import"),
            {"file": self.upload("shop: Test")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ProductInfo.objects.count(), 0)

    def test_invalid_yaml_returns_bad_request(self):
        response = self.client.post(
            reverse("price-import"),
            {"file": self.upload("goods: [")},
            HTTP_AUTHORIZATION=f"Token {self.supplier_token.key}",
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ProductInfo.objects.count(), 0)
