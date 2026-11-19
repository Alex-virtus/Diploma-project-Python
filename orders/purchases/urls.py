from django.urls import path

from .views import CartItemAddView, CartItemDetailView, CartView


urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemAddView.as_view(), name="cart-item-add"),
    path("cart/items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]
