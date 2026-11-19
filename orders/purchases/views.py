import logging

from decimal import Decimal
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from accounts.permissions import IsBuyer
from catalog.models import ProductInfo
from .models import Order, OrderItem
from .serializers import (
    CartItemAddSerializer,
    CartItemQuantitySerializer,
    CartItemSerializer,
    OrderConfirmationSerializer,
)


logger = logging.getLogger(__name__)


class CartView(APIView):
    permission_classes = [IsAuthenticated, IsBuyer]

    def get(self, request):
        basket = Order.objects.filter(
            user=request.user,
            state=Order.State.BASKET,
        ).first()

        if basket is None:
            items = []
        else:
            items = list(
                basket.items
                .select_related("product_info__product", "product_info__shop")
                .order_by("id")
            )

        total = sum(
            (
                item.product_info.price * item.quantity
                for item in items
            ),
            Decimal("0.00"),
        )

        return Response({
            "items": CartItemSerializer(items, many=True).data,
            "total": total,
        })


class CartItemAddView(APIView):
    permission_classes = [IsAuthenticated, IsBuyer]

    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_info_id = serializer.validated_data["product_info_id"]
        quantity_to_add = serializer.validated_data["quantity"]

        with transaction.atomic():
            product_info = get_object_or_404(
                ProductInfo.objects.select_for_update().select_related("shop"),
                pk=product_info_id,
            )

            if not product_info.shop.accepts_orders:
                return Response(
                    {"detail": "Поставщик временно не принимает заказы."},
                    status=status.HTTP_409_CONFLICT,
                )

            basket, _ = Order.objects.get_or_create(
                user=request.user,
                state=Order.State.BASKET,
            )

            item = (
                OrderItem.objects.select_for_update()
                .filter(order=basket, product_info=product_info)
                .first()
            )
            new_quantity = quantity_to_add + (item.quantity if item else 0)

            if new_quantity > product_info.quantity:
                return Response(
                    {
                        "detail": (
                            "Запрошенное количество превышает остаток "
                            "поставщика."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            created = item is None
            if created:
                item = OrderItem.objects.create(
                    order=basket,
                    product_info=product_info,
                    quantity=new_quantity,
                    unit_price=product_info.price,
                )
            else:
                item.quantity = new_quantity
                item.save(update_fields=["quantity"])

        response_status = (
            status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        return Response(
            CartItemSerializer(item).data,
            status=response_status,
        )


class CartItemDetailView(APIView):
    permission_classes = [IsAuthenticated, IsBuyer]

    def put(self, request, pk):
        serializer = CartItemQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_quantity = serializer.validated_data["quantity"]

        with transaction.atomic():
            item = get_object_or_404(
                OrderItem.objects
                .select_for_update()
                .select_related("product_info__shop"),
                pk=pk,
                order__user=request.user,
                order__state=Order.State.BASKET,
            )
            product_info = item.product_info

            if not product_info.shop.accepts_orders:
                return Response(
                    {"detail": "Поставщик временно не принимает заказы."},
                    status=status.HTTP_409_CONFLICT,
                )

            if requested_quantity > product_info.quantity:
                return Response(
                    {
                        "detail": (
                            "Запрошенное количество превышает остаток "
                            "поставщика."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item.quantity = requested_quantity
            item.save(update_fields=["quantity"])

        return Response(CartItemSerializer(item).data)

    def delete(self, request, pk):
        item = get_object_or_404(
            OrderItem.objects,
            pk=pk,
            order__user=request.user,
            order__state=Order.State.BASKET,
        )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderConfirmationView(APIView):
    permission_classes = [IsAuthenticated, IsBuyer]

    def post(self, request):
        serializer = OrderConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        address = get_object_or_404(
            Address,
            pk=serializer.validated_data["address_id"],
            user=request.user,
        )

        with transaction.atomic():
            basket = get_object_or_404(
                Order.objects.select_for_update(),
                user=request.user,
                state=Order.State.BASKET,
            )
            items = list(
                basket.items
                .select_for_update()
                .select_related("product_info__product", "product_info__shop")
                .order_by("product_info_id")
            )

            if not items:
                return Response(
                    {"detail": "Корзина пуста."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            offers = {
                offer.pk: offer
                for offer in ProductInfo.objects.select_for_update()
                .select_related("shop", "product")
                .filter(
                    pk__in=[item.product_info_id for item in items]
                )
                .order_by("pk")
            }

            for item in items:
                offer = offers[item.product_info_id]

                if not offer.shop.accepts_orders:
                    return Response(
                        {
                            "detail": (
                                f"Поставщик «{offer.shop.name}» "
                                "временно не принимает заказы."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if item.quantity > offer.quantity:
                    return Response(
                        {
                            "detail": (
                                f"Недостаточно товара «{offer.product.name}» "
                                "у поставщика."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            for item in items:
                offer = offers[item.product_info_id]
                offer.quantity -= item.quantity
                offer.save(update_fields=["quantity"])

                item.unit_price = offer.price
                item.save(update_fields=["unit_price"])

            basket.contact = address
            basket.state = Order.State.NEW
            basket.save(update_fields=["contact", "state"])

            order_id = basket.pk
            buyer_email = request.user.email
            address_text = (
                f"{address.city}, {address.street}, дом {address.house}, "
                f"корпус {address.structure}, строение {address.building}, "
                f"квартира {address.apartment}; телефон: {address.phone}"
            )
            order_lines = [
                (
                    f"- {item.product_info.product.name} "
                    f"({item.product_info.shop.name}): "
                    f"{item.quantity} x {item.unit_price} = "
                    f"{item.total_price}"
                )
                for item in items
            ]
            invoice_body = "\n".join(
                [
                    f"Заказ №{order_id}",
                    f"Покупатель: {buyer_email}",
                    f"Адрес доставки: {address_text}",
                    "",
                    *order_lines,
                    "",
                    f"Итого: {sum(item.total_price for item in items)}",
                ]
            )

        failed_notifications = []
        notifications = (
            (
                "покупателю",
                "Заказ принят",
                f"Ваш заказ №{order_id} принят.\n\n{invoice_body}",
                [buyer_email],
            ),
            (
                "администратору",
                f"Накладная по заказу №{order_id}",
                invoice_body,
                [settings.ORDER_ADMIN_EMAIL]
                if settings.ORDER_ADMIN_EMAIL
                else [],
            ),
        )

        for recipient_type, subject, message, recipients in notifications:
            if not recipients:
                logger.error(
                    "Не задан ORDER_ADMIN_EMAIL; накладную по заказу %s "
                    "отправить невозможно.",
                    order_id,
                )
                failed_notifications.append(recipient_type)
                continue

            try:
                sent_count = send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipients,
                    fail_silently=False,
                )
                if sent_count != 1:
                    logger.error(
                        "Письмо %s по заказу %s не отправлено.",
                        recipient_type,
                        order_id,
                    )
                    failed_notifications.append(recipient_type)
            except (SMTPException, OSError):
                logger.exception(
                    "Не удалось отправить письмо %s по заказу %s.",
                    recipient_type,
                    order_id,
                )
                failed_notifications.append(recipient_type)

        response_data = {
            "detail": f"Заказ №{order_id} оформлен.",
            "order_id": order_id,
            "state": Order.State.NEW,
            "notifications_failed": failed_notifications,
        }
        if failed_notifications:
            response_data["email_warning"] = (
                "Заказ сохранён, но некоторые письма не удалось отправить."
            )

        return Response(response_data, status=status.HTTP_201_CREATED)
