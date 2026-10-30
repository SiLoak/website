"""Collection point logic for the location module.

- Service type (jenis layanan) is derived from the point's name, so no schema
  change is needed in the waste app that owns CollectionPoint.
- Opening hours are parsed from free text such as "Senin - Sabtu, 08.00 - 16.00 WIB".
- Addresses and place searches use OpenStreetMap Nominatim, cached server side.
"""

import math
import re
import time as time_module
from dataclasses import dataclass
from datetime import time
from urllib.parse import urlencode

import requests
from django.core.cache import cache

PLACEHOLDER_ADDRESS = "Alamat belum tersedia"

CATEGORIES = (
    ("bank_sampah", "Bank sampah", ("bank sampah",)),
    ("ups", "Unit pengolahan sampah", ("ups ", "upk ", "sentra ups")),
    ("tps", "Tempat pengolahan sampah", ("tps", "tpst", "tppas")),
    ("tpa", "Tempat pemrosesan akhir", ("tpa ",)),
    ("kompos", "Pengomposan", ("kompos", "rumah kompos")),
    ("depo", "Depo sampah", ("depo",)),
)
OTHER_CATEGORY = ("lainnya", "Lainnya")

DAY_NAMES = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
_DAY_INDEX = {name.lower(): index for index, name in enumerate(DAY_NAMES)}
_DAY_INDEX["jum'at"] = 4
_DAY = r"(senin|selasa|rabu|kamis|jum'?at|sabtu|minggu)"
_DAYS_RE = re.compile(_DAY + r"(?:\s*-\s*" + _DAY + r")?", re.IGNORECASE)
_TIMES_RE = re.compile(r"(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:](\d{2})")

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_HEADERS = {"User-Agent": "SiLoak/1.0 (tugas kelompok PBP; siloak web app)"}
NOMINATIM_TIMEOUT = 6
GEOCODE_CACHE_SECONDS = 60 * 60 * 24
REVERSE_CACHE_SECONDS = 60 * 60 * 24 * 30


class GeocodingError(Exception):
    """OpenStreetMap could not be reached or answered with an error."""


def categorize(name):
    lowered = f"{name.lower()} "
    for value, label, prefixes in CATEGORIES:
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return value, label
    return OTHER_CATEGORY


def category_label(value):
    for category, label, _ in CATEGORIES:
        if category == value:
            return label
    return OTHER_CATEGORY[1]


@dataclass(frozen=True)
class OpeningHours:
    days: frozenset
    opens: time
    closes: time


def parse_hours(text):
    """Read "Senin - Sabtu, 08.30 - 17.00 WIB" into days and times, or None."""
    times = _TIMES_RE.search(text or "")
    if not times:
        return None
    open_h, open_m, close_h, close_m = (int(part) for part in times.groups())
    if not (0 <= open_h < 24 and 0 <= close_h < 24 and open_m < 60 and close_m < 60):
        return None

    days = _DAYS_RE.search(text[: times.start()])
    if days:
        first = _DAY_INDEX[days.group(1).lower()]
        last = _DAY_INDEX[(days.group(2) or days.group(1)).lower()]
        span = (last - first) % 7
        day_set = frozenset((first + offset) % 7 for offset in range(span + 1))
    else:
        day_set = frozenset(range(7))
    return OpeningHours(day_set, time(open_h, open_m), time(close_h, close_m))


def _clock(value):
    return f"{value.hour:02d}.{value.minute:02d}"


def opening_status(text, now):
    """Whether a point is open at ``now`` (aware datetime), with a short label."""
    hours = parse_hours(text)
    if hours is None:
        return {"is_open": None, "label": "Jam belum tersedia"}

    today, clock = now.weekday(), now.time()
    if today in hours.days and hours.opens <= clock < hours.closes:
        return {"is_open": True, "label": f"Buka sampai {_clock(hours.closes)}"}
    if today in hours.days and clock < hours.opens:
        return {"is_open": False, "label": f"Tutup · buka hari ini {_clock(hours.opens)}"}
    for offset in range(1, 8):
        day = (today + offset) % 7
        if day in hours.days:
            return {"is_open": False, "label": f"Tutup · buka {DAY_NAMES[day]} {_clock(hours.opens)}"}
    return {"is_open": False, "label": "Tutup"}  # pragma: no cover - parse_hours always yields a day


def distance_km(lat1, lng1, lat2, lng2):
    radians = math.radians
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(radians(lat1)) * math.cos(radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def directions_url(latitude, longitude, origin=None):
    start = f"{origin[0]},{origin[1]}" if origin else ""
    return "https://www.openstreetmap.org/directions?" + urlencode(
        {"engine": "fossgis_osrm_car", "route": f"{start};{latitude},{longitude}"}
    )


def serialize_point(point, now, origin=None):
    latitude, longitude = float(point.latitude), float(point.longitude)
    category, label = categorize(point.name)
    status = opening_status(point.operating_hours, now)
    distance = round(distance_km(origin[0], origin[1], latitude, longitude), 2) if origin else None
    has_address = point.address and point.address != PLACEHOLDER_ADDRESS
    return {
        "id": point.pk,
        "name": point.name,
        "address": point.address if has_address else "",
        "latitude": latitude,
        "longitude": longitude,
        "operating_hours": point.operating_hours,
        "is_open": status["is_open"],
        "opening_label": status["label"],
        "category": category,
        "category_label": label,
        "distance_km": distance,
        "directions_url": directions_url(latitude, longitude, origin),
    }


def active_points():
    from waste.models import CollectionPoint

    return CollectionPoint.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False)


def points_payload(origin=None):
    """Every active point, serialized like the API, sorted by name. Used by other modules' maps."""
    from django.utils import timezone

    now = timezone.localtime()
    rows = [serialize_point(point, now, origin) for point in active_points()]
    rows.sort(key=lambda row: row["name"].lower())
    return rows


def _clean_label(display_name):
    return re.sub(r",\s*Indonesia$", "", display_name or "").strip()


def _nominatim(path, params):
    try:
        response = requests.get(
            f"{NOMINATIM_URL}/{path}",
            params={"format": "jsonv2", "accept-language": "id", **params},
            headers=NOMINATIM_HEADERS,
            timeout=NOMINATIM_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        raise GeocodingError(str(error)) from error


def geocode(query):
    """Places in Indonesia matching ``query``, as label/latitude/longitude."""
    key = "location:geocode:" + re.sub(r"\s+", " ", query.strip().lower())
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = _nominatim("search", {"q": query.strip(), "countrycodes": "id", "limit": 5})
    results = [
        {"label": _clean_label(row.get("display_name")), "latitude": float(row["lat"]), "longitude": float(row["lon"])}
        for row in rows
        if row.get("lat") and row.get("lon")
    ]
    cache.set(key, results, GEOCODE_CACHE_SECONDS)
    return results


def reverse_geocode(latitude, longitude):
    key = f"location:reverse:{latitude:.5f}:{longitude:.5f}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _nominatim("reverse", {"lat": latitude, "lon": longitude, "zoom": 18})
    label = _clean_label(data.get("display_name")) if isinstance(data, dict) else ""
    cache.set(key, label, REVERSE_CACHE_SECONDS)
    return label


def throttle(request, scope, limit, period=60):
    """True when this client already made ``limit`` calls to ``scope`` in this window."""
    if request.user.is_authenticated:
        who = f"user:{request.user.pk}"
    else:
        who = f"ip:{request.META.get('REMOTE_ADDR', '')}"
    key = f"location:throttle:{scope}:{who}:{int(time_module.time() // period)}"
    if cache.add(key, 1, timeout=period):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:  # the key expired between add and incr
        cache.set(key, 1, timeout=period)
        return False
