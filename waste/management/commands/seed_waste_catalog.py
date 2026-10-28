from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from waste.catalog_seed import load_catalog_data, sync_catalog
from waste.models import CollectionPoint, WasteType


class Command(BaseCommand):
    help = "Seed jenis sampah dan titik pengumpulan dari waste.json/dropoff.json."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            points, waste_types = load_catalog_data(settings.BASE_DIR)
            counts = sync_catalog(CollectionPoint, WasteType, points, waste_types)
        except ValueError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Katalog disinkronkan: "
                f"{counts['waste_types_created']} jenis sampah dibuat, "
                f"{counts['waste_types_updated']} diperbarui; "
                f"{counts['points_created']} titik dibuat, "
                f"{counts['points_updated']} diperbarui. "
                f"Sampel lama dinonaktifkan: "
                f"{counts['legacy_waste_types_disabled']} jenis sampah, "
                f"{counts['legacy_points_disabled']} titik."
            )
        )
