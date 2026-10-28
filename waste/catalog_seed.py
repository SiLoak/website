import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


LEGACY_WASTE_TYPE_NAMES = (
    "Kardus (Campur & Bersih)",
    "Kertas Koran / Majalah",
    "Buku Pelajaran Bekas",
    "Botol plastik (PET bening)",
    "Gelas Plastik Bersih (PP)",
    "Jeriken & Tutup Galon (HDPE)",
)

LEGACY_COLLECTION_POINT_NAMES = (
    "Depo Pasar Minggu",
    "Bank Sampah Tebet Hijau",
    "Depo Lenteng Agung Berseri",
)


def _read_json(path):
    try:
        with path.open(encoding="utf-8") as data_file:
            return json.load(data_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Tidak dapat membaca {path.name}: {error}") from error


def load_catalog_data(data_dir):
    data_dir = Path(data_dir)
    raw_points = _read_json(data_dir / "dropoff.json")
    raw_waste_types = _read_json(data_dir / "waste.json")

    if not isinstance(raw_points, list) or not isinstance(raw_waste_types, list):
        raise ValueError("dropoff.json dan waste.json harus berisi array JSON.")

    points = []
    point_names = set()
    for row_number, row in enumerate(raw_points, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"dropoff.json baris {row_number} harus berupa objek.")
        name = str(row.get("name", "")).strip()
        if not name or name in point_names:
            raise ValueError(
                f"Nama titik pengumpulan kosong atau duplikat di baris {row_number}."
            )
        try:
            latitude = Decimal(str(row["latitude"]))
            longitude = Decimal(str(row["longitude"]))
        except (KeyError, InvalidOperation, TypeError) as error:
            raise ValueError(
                f"Koordinat titik pengumpulan tidak valid di baris {row_number}."
            ) from error
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"Koordinat di baris {row_number} di luar rentang.")
        points.append(
            {
                "name": name,
                "address": "Alamat belum tersedia",
                "operating_hours": "",
                "latitude": latitude.quantize(Decimal("0.000001")),
                "longitude": longitude.quantize(Decimal("0.000001")),
            }
        )
        point_names.add(name)

    waste_types = []
    waste_names = set()
    for row_number, row in enumerate(raw_waste_types, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"waste.json baris {row_number} harus berupa objek.")
        name = str(row.get("name", "")).strip()
        category = str(row.get("tipe", "")).strip()
        if not name or not category or name in waste_names:
            raise ValueError(
                f"Nama atau kategori jenis sampah kosong/duplikat di baris {row_number}."
            )
        try:
            rate = Decimal(str(row["price"]))
        except (KeyError, InvalidOperation, TypeError) as error:
            raise ValueError(f"Harga tidak valid di baris {row_number}.") from error
        if rate < 0:
            raise ValueError(f"Harga tidak boleh negatif di baris {row_number}.")
        waste_types.append(
            {"name": name, "category": category, "rate_per_kg": rate}
        )
        waste_names.add(name)

    return points, waste_types


def sync_catalog(CollectionPoint, WasteType, points, waste_types):
    counts = {
        "points_created": 0,
        "points_updated": 0,
        "waste_types_created": 0,
        "waste_types_updated": 0,
    }

    for row in points:
        matches = CollectionPoint.objects.filter(name=row["name"]).order_by("pk")
        point = matches.first()
        if point is None:
            CollectionPoint.objects.create(**row, is_active=True)
            counts["points_created"] += 1
            continue
        for field, value in row.items():
            setattr(point, field, value)
        point.is_active = True
        point.save()
        matches.exclude(pk=point.pk).update(is_active=False)
        counts["points_updated"] += 1

    for row in waste_types:
        _, created = WasteType.objects.update_or_create(
            name=row["name"], defaults={**row, "is_active": True}
        )
        counts["waste_types_created" if created else "waste_types_updated"] += 1

    current_point_names = [row["name"] for row in points]
    current_waste_names = [row["name"] for row in waste_types]
    counts["legacy_points_disabled"] = CollectionPoint.objects.filter(
        name__in=LEGACY_COLLECTION_POINT_NAMES
    ).exclude(name__in=current_point_names).update(is_active=False)
    counts["legacy_waste_types_disabled"] = WasteType.objects.filter(
        name__in=LEGACY_WASTE_TYPE_NAMES
    ).exclude(name__in=current_waste_names).update(is_active=False)
    return counts
