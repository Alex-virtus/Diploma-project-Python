from rest_framework import serializers

from .models import ProductInfo, ProductParameter


class ProductParameterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="parameter.name", read_only=True)

    class Meta:
        model = ProductParameter
        fields = ("name", "value")


class ProductInfoSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="product.name", read_only=True)
    description = serializers.CharField(
        source="product.description",
        read_only=True,
    )
    supplier = serializers.CharField(source="shop.name", read_only=True)
    category = serializers.CharField(
        source="product.category.name",
        read_only=True,
    )
    parameters = ProductParameterSerializer(many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = (
            "id",
            "name",
            "description",
            "supplier",
            "category",
            "parameters",
            "price",
            "price_rrc",
            "quantity",
        )
