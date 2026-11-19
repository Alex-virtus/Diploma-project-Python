from django.urls import path

from .views import ProductListView, PriceImportView

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    path("import/", PriceImportView.as_view(), name="price-import"),
]