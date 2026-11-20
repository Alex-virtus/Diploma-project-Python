from decimal import Decimal

from django.core import mail
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Address
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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ORDER_ADMIN_EMAIL="admin@example.com",
)
class OrderConfirmationAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            email="order-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.other_buyer = User.objects.create_user(
            email="other-order-buyer@example.com",
            password="Test-password-123!",
            role=User.Role.BUYER,
            is_active=True,
        )
        cls.supplier_one = User.objects.create_user(
            email="order-supplier-one@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )
        cls.supplier_two = User.objects.create_user(
            email="order-supplier-two@example.com",
            password="Test-password-123!",
            role=User.Role.SUPPLIER,
            is_active=True,
        )

        cls.shop_one = Shop.objects.create(
            name="Order Shop One",
            user=cls.supplier_one,
            accepts_orders=True,
        )
        cls.shop_two = Shop.objects.create(
            name="Order Shop Two",
            user=cls.supplier_two,
            accepts_orders=True,
        )

        category = Category.objects.create(name="Order Category")
        product_one = Product.objects.create(
            category=category,
            name="Order Product One",
        )
        product_two = Product.objects.create(
            category=category,
            name="Order Product Two",
        )

        cls.offer_one = ProductInfo.objects.create(
            product=product_one,
            shop=cls.shop_one,
            external_id=3001,
            quantity=5,
            price=Decimal("10.00"),
            price_rrc=Decimal("12.00"),
        )
        cls.offer_two = ProductInfo.objects.create(
            product=product_two,
            shop=cls.shop_two,
            external_id=3002,
            quantity=4,
            price=Decimal("7.50"),
            price_rrc=Decimal("9.00"),
        )

        cls.address = Address.objects.create(
            user=cls.buyer,
            city="Москва",
            street="Ленина",
            house="10",
            structure="",
            building="",
            apartment="5",
            phone="+79990000001",
        )
        cls.other_address = Address.objects.create(
            user=cls.other_buyer,
            city="Казань",
            street="Пушкина",
            house="5",
            structure="",
            building="",
            apartment="",
            phone="+79990000002",
        )

        cls.buyer_token = Token.objects.create(user=cls.buyer)

    def setUp(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.buyer_token.key}"
        )

    def create_basket(self, *offer_quantities):
        basket = Order.objects.create(user=self.buyer)
        for offer, quantity in offer_quantities:
            OrderItem.objects.create(
                order=basket,
                product_info=offer,
                quantity=quantity,
                unit_price=offer.price,
            )
        return basket

    def confirm_order(self, address=None):
        return self.client.post(
            reverse("order-confirmation"),
            {"address_id": (address or self.address).id},
            format="json",
        )

    def test_confirms_order_updates_stock_and_sends_both_emails(self):
        basket = self.create_basket(
            (self.offer_one, 2),
            (self.offer_two, 1),
        )

        response = self.confirm_order()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        basket.refresh_from_db()
        self.assertEqual(basket.state, Order.State.NEW)
        self.assertEqual(basket.contact, self.address)

        self.offer_one.refresh_from_db()
        self.offer_two.refresh_from_db()
        self.assertEqual(self.offer_one.quantity, 3)
        self.assertEqual(self.offer_two.quantity, 3)

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.buyer.email])
        self.assertEqual(mail.outbox[1].to, ["admin@example.com"])
        self.assertIn("Order Product One", mail.outbox[1].body)
        self.assertIn("Итого: 27.50", mail.outbox[1].body)
        self.assertEqual(response.data["notifications_failed"], [])

    def test_empty_basket_cannot_be_confirmed(self):
        basket = self.create_basket()

        response = self.confirm_order()

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        basket.refresh_from_db()
        self.assertEqual(basket.state, Order.State.BASKET)
        self.assertEqual(len(mail.outbox), 0)

    def test_insufficient_stock_does_not_confirm_or_send_emails(self):
        basket = self.create_basket((self.offer_one, 2))
        self.offer_one.quantity = 1
        self.offer_one.save(update_fields=["quantity"])

        response = self.confirm_order()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        basket.refresh_from_db()
        self.offer_one.refresh_from_db()
        self.assertEqual(basket.state, Order.State.BASKET)
        self.assertEqual(self.offer_one.quantity, 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_supplier_not_accepting_orders_prevents_confirmation(self):
        basket = self.create_basket((self.offer_one, 1))
        self.shop_one.accepts_orders = False
        self.shop_one.save(update_fields=["accepts_orders"])

        response = self.confirm_order()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        basket.refresh_from_db()
        self.offer_one.refresh_from_db()
        self.assertEqual(basket.state, Order.State.BASKET)
        self.assertEqual(self.offer_one.quantity, 5)
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_confirm_order_with_another_users_address(self):
        basket = self.create_basket((self.offer_one, 1))

        response = self.confirm_order(address=self.other_address)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        basket.refresh_from_db()
        self.assertEqual(basket.state, Order.State.BASKET)
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_user_cannot_confirm_order(self):
        self.create_basket((self.offer_one, 1))
        self.client.credentials()

        response = self.confirm_order()

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_order_history_lists_only_own_confirmed_orders(self):
        order = Order.objects.create(
            user=self.buyer,
            state=Order.State.NEW,
            contact=self.address,
        )
        OrderItem.objects.create(
            order=order,
            product_info=self.offer_one,
            quantity=2,
            unit_price=Decimal("9.00"),
        )

        self.create_basket((self.offer_two, 1))
        Order.objects.create(
            user=self.other_buyer,
            state=Order.State.NEW,
            contact=self.other_address,
        )

        response = self.client.get(reverse("order-confirmation"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], order.id)
        self.assertEqual(response.data[0]["state"], Order.State.NEW)
        self.assertEqual(
            Decimal(str(response.data[0]["total"])),
            Decimal("18.00"),
        )
        self.assertEqual(
            response.data[0]["items"][0]["unit_price"],
            "9.00",
        )

    def test_order_detail_returns_saved_order_data(self):
        order = Order.objects.create(
            user=self.buyer,
            state=Order.State.NEW,
            contact=self.address,
        )
        OrderItem.objects.create(
            order=order,
            product_info=self.offer_one,
            quantity=2,
            unit_price=Decimal("9.00"),
        )

        response = self.client.get(
            reverse("order-detail", kwargs={"pk": order.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], order.id)
        self.assertEqual(response.data["contact"]["id"], self.address.id)
        self.assertEqual(
            Decimal(str(response.data["total"])),
            Decimal("18.00"),
        )
        self.assertEqual(
            response.data["items"][0]["unit_price"],
            "9.00",
        )

    def test_buyer_cannot_view_another_users_order(self):
        order = Order.objects.create(
            user=self.other_buyer,
            state=Order.State.NEW,
            contact=self.other_address,
        )

        response = self.client.get(
            reverse("order-detail", kwargs={"pk": order.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_user_cannot_view_order_history(self):
        self.client.credentials()

        response = self.client.get(reverse("order-confirmation"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_supplier_cannot_view_order_history(self):
        supplier_token, _ = Token.objects.get_or_create(
            user=self.supplier_one
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {supplier_token.key}"
        )

        response = self.client.get(reverse("order-confirmation"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
