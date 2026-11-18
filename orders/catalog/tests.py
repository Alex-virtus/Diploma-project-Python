from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
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
