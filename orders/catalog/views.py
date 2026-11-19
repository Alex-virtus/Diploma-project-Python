import yaml

from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProductInfo
from .serializers import ProductInfoSerializer
from .permissions import IsSupplier
from .services import PriceImportError, import_shop_data


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


class PriceImportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsSupplier]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "Передайте YAML-файл в поле 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = yaml.safe_load(uploaded_file.read())
        except (yaml.YAMLError, UnicodeDecodeError):
            return Response(
                {"detail": "Не удалось прочитать корректный YAML-файл."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            shop = import_shop_data(data, request.user)
        except PriceImportError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": f"Прайс магазина «{shop.name}» обновлён.",
                "imported": len(data["goods"]),
            },
            status=status.HTTP_200_OK,
        )
