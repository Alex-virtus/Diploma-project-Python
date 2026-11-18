from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import (
    Category,
    Parameter,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
    ShopCategory,
)


class PriceImportError(ValueError):
    """Ошибка формата или содержимого прайса."""


def validate_price_data(data):
    if not isinstance(data, dict):
        raise PriceImportError("Корень YAML должен содержать объект.")

    shop_name = data.get("shop")
    categories = data.get("categories")
    goods = data.get("goods")

    if not isinstance(shop_name, str) or not shop_name.strip():
        raise PriceImportError("В YAML не указано название магазина.")
    if len(shop_name) > 50:
        raise PriceImportError("Название магазина длиннее 50 символов.")
    if not isinstance(categories, list) or not categories:
        raise PriceImportError(
            "В YAML отсутствует непустой список categories."
        )
    if not isinstance(goods, list):
        raise PriceImportError("В YAML отсутствует список goods.")

    category_ids = set()

    for category in categories:
        if not isinstance(category, dict):
            raise PriceImportError("Каждая категория должна быть объектом.")

        external_id = category.get("id")
        name = category.get("name")

        if type(external_id) is not int or external_id <= 0:
            raise PriceImportError(
                "У категории должен быть положительный целый id."
            )
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 100
        ):
            raise PriceImportError(
                "У категории должно быть корректное название."
            )
        if external_id in category_ids:
            raise PriceImportError(
                f"Повторяется id категории {external_id}."
            )

        category_ids.add(external_id)

    product_ids = set()
    required_fields = {
        "id",
        "category",
        "name",
        "price",
        "price_rrc",
        "quantity",
        "parameters",
    }

    for item in goods:
        if not isinstance(item, dict) or not required_fields.issubset(item):
            raise PriceImportError(
                "У товарной записи отсутствуют обязательные поля."
            )

        external_id = item["id"]

        if type(external_id) is not int or external_id <= 0:
            raise PriceImportError(
                "У товара должен быть положительный целый id."
            )
        if external_id in product_ids:
            raise PriceImportError(
                f"Повторяется id товара {external_id}."
            )

        product_ids.add(external_id)

        category_id = item["category"]
        if type(category_id) is not int or category_id <= 0:
            raise PriceImportError(
                f"У товара {external_id} ID категории должен быть "
                "положительным целым числом."
            )
        if category_id not in category_ids:
            raise PriceImportError(
                f"Для товара {external_id} не найдена категория "
                f"{category_id}."
            )

        if not isinstance(item["name"], str) or not item["name"].strip():
            raise PriceImportError(
                f"У товара {external_id} некорректное название."
            )
        if len(item["name"]) > 255:
            raise PriceImportError(
                f"Название товара {external_id} длиннее 255 символов."
            )
        if type(item["quantity"]) is not int or item["quantity"] < 0:
            raise PriceImportError(
                f"У товара {external_id} некорректное количество."
            )
        if not isinstance(item["parameters"], dict):
            raise PriceImportError(
                f"Характеристики товара {external_id} должны быть объектом."
            )

        for field in ("price", "price_rrc"):
            try:
                price = Decimal(str(item[field]))
            except (InvalidOperation, ValueError):
                raise PriceImportError(
                    f"У товара {external_id} некорректное поле {field}."
                )

            if not price.is_finite() or price < 0:
                raise PriceImportError(
                    f"У товара {external_id} поле {field} должно быть "
                    "конечным неотрицательным числом."
                )

        for name, value in item["parameters"].items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or len(name) > 100
            ):
                raise PriceImportError(
                    f"У товара {external_id} некорректное название "
                    "характеристики."
                )
            if not isinstance(value, (str, int, float, bool)):
                raise PriceImportError(
                    f"У товара {external_id} некорректное значение "
                    "характеристики."
                )
            if len(str(value)) > 255:
                raise PriceImportError(
                    f"Значение характеристики товара {external_id} "
                    "длиннее 255 символов."
                )


def import_shop_data(data, supplier):
    validate_price_data(data)

    with transaction.atomic():
        shop, created = Shop.objects.get_or_create(
            user=supplier,
            defaults={"name": data["shop"]},
        )

        if not created and shop.name != data["shop"]:
            shop.name = data["shop"]
            shop.save(update_fields=["name"])

        ShopCategory.objects.filter(shop=shop).delete()
        categories_by_external_id = {}

        for category_data in data["categories"]:
            category, _ = Category.objects.get_or_create(
                name=category_data["name"]
            )
            ShopCategory.objects.create(
                shop=shop,
                category=category,
                external_id=category_data["id"],
            )
            categories_by_external_id[category_data["id"]] = category

        imported_external_ids = []

        for item in data["goods"]:
            category = categories_by_external_id[item["category"]]
            product, _ = Product.objects.get_or_create(
                category=category,
                name=item["name"],
            )

            offer, _ = ProductInfo.objects.update_or_create(
                shop=shop,
                external_id=item["id"],
                defaults={
                    "product": product,
                    "model": item.get("model", ""),
                    "quantity": item["quantity"],
                    "price": Decimal(str(item["price"])),
                    "price_rrc": Decimal(str(item["price_rrc"])),
                },
            )
            imported_external_ids.append(item["id"])

            offer.parameters.all().delete()
            for name, value in item["parameters"].items():
                parameter, _ = Parameter.objects.get_or_create(name=name)
                ProductParameter.objects.create(
                    product_info=offer,
                    parameter=parameter,
                    value=str(value),
                )

        ProductInfo.objects.filter(shop=shop).exclude(
            external_id__in=imported_external_ids
        ).update(quantity=0)

    return shop
