from rest_framework import serializers

from accounts.serializers import AddressSerializer
from .models import OrderItem, Order


class CartItemSerializer(serializers.ModelSerializer):
    product_info = serializers.IntegerField(
        source="product_info_id",
        read_only=True,
    )
    name = serializers.CharField(
        source="product_info.product.name",
        read_only=True,
    )
    supplier = serializers.CharField(
        source="product_info.shop.name",
        read_only=True,
    )
    price = serializers.DecimalField(
        source="product_info.price",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_info",
            "name",
            "supplier",
            "price",
            "quantity",
            "total",
        )
        read_only_fields = fields

    def get_total(self, obj):
        return obj.product_info.price * obj.quantity


class CartItemAddSerializer(serializers.Serializer):
    product_info_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class CartItemQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class OrderConfirmationSerializer(serializers.Serializer):
    address_id = serializers.IntegerField(min_value=1)


class OrderItemHistorySerializer(serializers.ModelSerializer):
    product_info = serializers.IntegerField(
        source="product_info_id",
        read_only=True,
    )
    name = serializers.CharField(
        source="product_info.product.name",
        read_only=True,
    )
    supplier = serializers.CharField(
        source="product_info.shop.name",
        read_only=True,
    )
    total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "product_info",
            "name",
            "supplier",
            "quantity",
            "unit_price",
            "total",
        )

    def get_total(self, obj):
        return obj.total_price


class OrderHistorySerializer(serializers.ModelSerializer):
    contact = AddressSerializer(read_only=True)
    items = OrderItemHistorySerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ("id", "dt", "state", "contact", "items", "total")

    def get_total(self, obj):
        return sum(
            (item.total_price for item in obj.items.all()),
            start=0,
        )
