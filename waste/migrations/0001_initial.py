from decimal import Decimal

import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_catalog(apps, schema_editor):
    WasteType = apps.get_model("waste", "WasteType")
    CollectionPoint = apps.get_model("waste", "CollectionPoint")

    waste_types = [
        ("Kardus (Campur & Bersih)", Decimal("5000.00")),
        ("Kertas Koran / Majalah", None),
        ("Buku Pelajaran Bekas", None),
        ("Botol plastik (PET bening)", Decimal("8000.00")),
        ("Gelas Plastik Bersih (PP)", None),
        ("Jeriken & Tutup Galon (HDPE)", None),
    ]
    for name, rate in waste_types:
        WasteType.objects.get_or_create(name=name, defaults={"rate_per_kg": rate})

    collection_points = [
        (
            "Depo Pasar Minggu",
            "Jl. Raya Pasar Minggu No. 14, RT 02 / RW 08, Pasar Minggu",
            "Senin - Sabtu, 08.00 - 16.00 WIB",
        ),
        (
            "Bank Sampah Tebet Hijau",
            "Jl. Tebet Barat Dalam Raya No. 42, Tebet",
            "Senin - Sabtu, 08.30 - 17.00 WIB",
        ),
        (
            "Depo Lenteng Agung Berseri",
            "Jl. Raya Lenteng Agung No. 8, Jagakarsa",
            "Senin - Sabtu, 08.00 - 15.30 WIB",
        ),
    ]
    for name, address, operating_hours in collection_points:
        CollectionPoint.objects.get_or_create(
            name=name,
            defaults={"address": address, "operating_hours": operating_hours},
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="CollectionPoint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("address", models.CharField(max_length=255)),
                ("operating_hours", models.CharField(blank=True, max_length=120)),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Menunggu penimbangan"),
                            ("verified", "Terverifikasi"),
                            ("canceled", "Dibatalkan"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "collection_point",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to="waste.collectionpoint",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="waste_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="verified_waste_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="WasteType",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                (
                    "rate_per_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SubmissionItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "estimated_weight",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                (
                    "actual_weight",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                (
                    "unit_rate_snapshot",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="waste.submission",
                    ),
                ),
                (
                    "waste_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submission_items",
                        to="waste.wastetype",
                    ),
                ),
            ],
            options={"ordering": ["pk"]},
        ),
        migrations.AddConstraint(
            model_name="submissionitem",
            constraint=models.UniqueConstraint(
                fields=("submission", "waste_type"),
                name="unique_waste_type_per_submission",
            ),
        ),
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
