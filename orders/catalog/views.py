from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny

from .models import ProductInfo
from .serializers import ProductInfoSerializer


class ProductListView(generics.ListAPIView):
    serializer_class = ProductInfoSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = (
            ProductInfo.objects
            .select_related("product", "product__category", "shop")
            .prefetch_related("parameters__parameter")
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search)
                | Q(product__description__icontains=search)
                | Q(shop__name__icontains=search)
                | Q(product__category__name__icontains=search)
            )

        for param, field in (
            ("category_id", "product__category_id"),
            ("shop_id", "shop_id"),
        ):
            value = self.request.query_params.get(param)
            if value is not None:
                try:
                    object_id = int(value)
                    if object_id < 1:
                        raise ValueError
                except ValueError:
                    raise ValidationError({
                        param: "Укажите положительный целый ID."
                    })
                queryset = queryset.filter(**{field: object_id})

        return queryset
