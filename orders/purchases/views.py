from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsBuyer
from catalog.models import ProductInfo
from .models import Order, OrderItem
from .serializers import (
    CartItemAddSerializer,
    CartItemQuantitySerializer,
    CartItemSerializer,
)


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
