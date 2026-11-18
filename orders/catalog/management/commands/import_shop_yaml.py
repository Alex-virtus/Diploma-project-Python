from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from catalog.services import PriceImportError, import_shop_data


class Command(BaseCommand):
    help = "Импортирует прайс магазина из YAML-файла"

    def add_arguments(self, parser):
        parser.add_argument("yaml_path", type=Path)
        parser.add_argument("--supplier-email", required=True)

    def handle(self, *args, **options):
        yaml_path = options["yaml_path"].expanduser()

        try:
            with yaml_path.open(encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except (OSError, yaml.YAMLError) as error:
            raise CommandError(
                f"Не удалось прочитать YAML-файл: {error}"
            ) from error

        User = get_user_model()
        supplier = User.objects.filter(
            email__iexact=options["supplier_email"],
            role=User.Role.SUPPLIER,
            is_active=True,
        ).first()

        if supplier is None:
            raise CommandError(
                "Не найден активный пользователь-поставщик с таким email."
            )

        try:
            shop = import_shop_data(data, supplier)
        except PriceImportError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Прайс магазина {shop.name} импортирован: "
                f"{len(data['goods'])} товарных предложений."
            )
        )
