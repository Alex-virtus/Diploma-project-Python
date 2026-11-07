from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Order(models.Model):
    class State(models.TextChoices):
        BASKET = "basket", "Корзина"
        NEW = "new", "Новый"
        CONFIRMED = "confirmed", "Подтвержден"
        ASSEMBLED = "assembled", "Собран"
        SENT = "sent", "Отправлен"
        DELIVERED = "delivered", "Доставлен"
        CANCELED = "canceled", "Отменен"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name="Покупатель",
    )
    contact = models.ForeignKey(
        "accounts.Address",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Адрес доставки",
    )
    dt = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    state = models.CharField(
        max_length=15,
        choices=State.choices,
        default=State.BASKET,
        verbose_name="Статус",
    )

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-dt"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(state="basket"),
                name="unique_basket_per_user",
            ),
        ]

    def __str__(self):
        return f"Заказ №{self.pk} - {self.get_state_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ",
    )
    product_info = models.ForeignKey(
        "catalog.ProductInfo",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Предложение товара",
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Количество",
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Цена за единицу на момент заказа",
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product_info"],
                name="unique_product_info_per_order",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="order_item_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.product_info} - {self.quantity}"

    @property
    def total_price(self):
        return self.unit_price * self.quantity
