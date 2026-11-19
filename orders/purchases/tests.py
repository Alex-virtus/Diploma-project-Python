from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from catalog.models import Category, Product, ProductInfo, Shop

from .models import Order, OrderItem


User = get_user_model()


class CartAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            email="cart-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.other_buyer = User.objects.create_user(
            email="other-cart-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.supplier_one = User.objects.create_user(
            email="cart-supplier-one@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )
        cls.supplier_two = User.objects.create_user(
            email="cart-supplier-two@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )
        cls.supplier_token = Token.objects.create(user=cls.supplier_one)

        cls.shop_one = Shop.objects.create(
            name="Cart Shop One",
            user=cls.supplier_one,
            accepts_orders=True,
        )
        cls.shop_two = Shop.objects.create(
            name="Cart Shop Two",
            user=cls.supplier_two,
            accepts_orders=True,
        )

        category = Category.objects.create(name="Cart Category")
        product_one = Product.objects.create(
            category=category,
            name="Cart Product One",
        )
        product_two = Product.objects.create(
            category=category,
            name="Cart Product Two",
        )

        cls.offer_one = ProductInfo.objects.create(
            product=product_one,
            shop=cls.shop_one,
            external_id=1001,
            quantity=5,
            price=Decimal("10.00"),
            price_rrc=Decimal("12.00"),
        )
        cls.offer_two = ProductInfo.objects.create(
            product=product_two,
            shop=cls.shop_two,
            external_id=2001,
            quantity=4,
            price=Decimal("7.50"),
            price_rrc=Decimal("9.00"),
        )

    def setUp(self):
        token, _ = Token.objects.get_or_create(user=self.buyer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def add_item(self, offer, quantity):
        return self.client.post(
            reverse("cart-item-add"),
            {"product_info_id": offer.id, "quantity": quantity},
            format="json",
        )

    def test_empty_cart_returns_no_items_and_zero_total(self):
        response = self.client.get(reverse("cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(Decimal(str(response.data["total"])), Decimal("0.00"))

    def test_can_add_products_from_different_shops(self):
        first_response = self.add_item(self.offer_one, 2)
        second_response = self.add_item(self.offer_two, 1)

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reverse("cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 2)
        self.assertEqual(Decimal(str(response.data["total"])), Decimal("27.50"))

    def test_readding_product_increases_quantity(self):
        self.add_item(self.offer_one, 2)

        response = self.add_item(self.offer_one, 1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = OrderItem.objects.get(
            order__user=self.buyer,
            product_info=self.offer_one,
        )
        self.assertEqual(item.quantity, 3)

    def test_add_rejects_quantity_above_stock(self):
        response = self.add_item(self.offer_one, 6)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            OrderItem.objects.filter(
                order__user=self.buyer,
                product_info=self.offer_one,
            ).exists()
        )

    def test_readding_rejects_total_quantity_above_stock(self):
        self.add_item(self.offer_one, 4)

        response = self.add_item(self.offer_one, 2)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item = OrderItem.objects.get(
            order__user=self.buyer,
            product_info=self.offer_one,
        )
        self.assertEqual(item.quantity, 4)

    def test_cannot_add_when_supplier_is_not_accepting_orders(self):
        self.shop_one.accepts_orders = False
        self.shop_one.save(update_fields=["accepts_orders"])

        response = self.add_item(self.offer_one, 1)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(
            OrderItem.objects.filter(
                order__user=self.buyer,
                product_info=self.offer_one,
            ).exists()
        )

    def test_can_set_cart_item_quantity(self):
        self.add_item(self.offer_one, 1)
        item = OrderItem.objects.get(
            order__user=self.buyer,
            product_info=self.offer_one,
        )

        response = self.client.put(
            reverse("cart-item-detail", kwargs={"pk": item.pk}),
            {"quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_cannot_set_quantity_above_stock(self):
        self.add_item(self.offer_one, 1)
        item = OrderItem.objects.get(
            order__user=self.buyer,
            product_info=self.offer_one,
        )

        response = self.client.put(
            reverse("cart-item-detail", kwargs={"pk": item.pk}),
            {"quantity": 6},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_can_delete_own_cart_item(self):
        self.add_item(self.offer_one, 1)
        item = OrderItem.objects.get(
            order__user=self.buyer,
            product_info=self.offer_one,
        )

        response = self.client.delete(
            reverse("cart-item-detail", kwargs={"pk": item.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(OrderItem.objects.filter(pk=item.pk).exists())

    def test_cannot_delete_another_users_cart_item(self):
        other_order = Order.objects.create(user=self.other_buyer)
        other_item = OrderItem.objects.create(
            order=other_order,
            product_info=self.offer_one,
            quantity=1,
            unit_price=self.offer_one.price,
        )

        response = self.client.delete(
            reverse("cart-item-detail", kwargs={"pk": other_item.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(OrderItem.objects.filter(pk=other_item.pk).exists())

    def test_anonymous_user_cannot_view_cart(self):
        self.client.credentials()

        response = self.client.get(reverse("cart"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_supplier_cannot_use_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.supplier_token.key}"
        )

        response = self.client.get(reverse("cart"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
