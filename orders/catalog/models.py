from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Shop(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название")
    url = models.URLField(blank=True, null=True, verbose_name="Ссылка на прайс")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shop",
        verbose_name="Пользователь-поставщик",
    )
    accepts_orders = models.BooleanField(
        default=True,
        verbose_name="Принимает заказы",
    )

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Магазины"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название")
    shops = models.ManyToManyField(
        Shop,
        through="ShopCategory",
        related_name="categories",
        verbose_name="Магазины",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ShopCategory(models.Model):
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="category_links",
        verbose_name="Магазин",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="shop_links",
        verbose_name="Категория",
    )
    external_id = models.PositiveBigIntegerField(
        verbose_name="Внешний ID категории у поставщика",
    )

    class Meta:
        verbose_name = "Категория магазина"
        verbose_name_plural = "Категории магазинов"
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "external_id"],
                name="unique_shop_external_category",
            ),
            models.UniqueConstraint(
                fields=["shop", "category"],
                name="unique_shop_category",
            ),
        ]

    def __str__(self):
        return f"{self.shop}: {self.category}"


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Категория",
    )
    name = models.CharField(max_length=255, verbose_name="Название")

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name="Товар",
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name="Магазин",
    )
    external_id = models.PositiveBigIntegerField(
        verbose_name="Внешний ID товара у поставщика",
    )
    model = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Модель",
    )
    quantity = models.PositiveIntegerField(verbose_name="Остаток")
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Цена",
    )
    price_rrc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Рекомендованная розничная цена",
    )

    class Meta:
        verbose_name = "Предложение товара"
        verbose_name_plural = "Предложения товаров"
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "external_id"],
                name="unique_shop_external_product",
            ),
        ]

    def __str__(self):
        return f"{self.product} — {self.shop}"


class Parameter(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название характеристики",
    )

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    product_info = models.ForeignKey(
        ProductInfo,
        on_delete=models.CASCADE,
        related_name="parameters",
        verbose_name="Предложение товара",
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE,
        related_name="product_values",
        verbose_name="Характеристика",
    )
    value = models.CharField(max_length=255, verbose_name="Значение")

    class Meta:
        verbose_name = "Значение характеристики"
        verbose_name_plural = "Значения характеристик"
        constraints = [
            models.UniqueConstraint(
                fields=["product_info", "parameter"],
                name="unique_offer_parameter",
            ),
        ]

    def __str__(self):
        return f"{self.parameter}: {self.value}"
