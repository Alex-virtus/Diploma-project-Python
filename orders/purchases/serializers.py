from rest_framework import serializers

from .models import OrderItem


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
