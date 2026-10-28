from django.conf import settings
from django.db import migrations, models

from waste.catalog_seed import load_catalog_data, sync_catalog


def seed_catalog_from_json(apps, schema_editor):
    CollectionPoint = apps.get_model("waste", "CollectionPoint")
    WasteType = apps.get_model("waste", "WasteType")
    points, waste_types = load_catalog_data(settings.BASE_DIR)
    sync_catalog(CollectionPoint, WasteType, points, waste_types)


class Migration(migrations.Migration):
    dependencies = [
        ("waste", "0002_submission_incentive_allocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="wastetype",
            name="category",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.RunPython(seed_catalog_from_json, migrations.RunPython.noop),
    ]
