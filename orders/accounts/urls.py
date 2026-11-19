from django.urls import path

from .views import RegisterView, ConfirmEmailView, LoginView, AddressListCreateView, AddressDeleteView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("confirm-email/", ConfirmEmailView.as_view(), name="confirm-email"),
    path("login/", LoginView.as_view(), name="login"),
    path("addresses/", AddressListCreateView.as_view(), name="address-list"),
    path("addresses/<int:pk>/", AddressDeleteView.as_view(), name="address-delete"),
]
