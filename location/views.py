from django import forms
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from waste.models import CollectionPoint

from . import services

GEOCODE_LIMIT_PER_MINUTE = 10
ADDRESS_LIMIT_PER_MINUTE = 30


class PointQueryForm(forms.Form):
    q = forms.CharField(required=False, max_length=80)
    lat = forms.FloatField(required=False, min_value=-90, max_value=90)
    lng = forms.FloatField(required=False, min_value=-180, max_value=180)
    radius = forms.FloatField(required=False, min_value=0.1, max_value=100)
    category = forms.CharField(required=False, max_length=30)
    open_now = forms.BooleanField(required=False)
    sort = forms.ChoiceField(required=False, choices=(("nearest", "Terdekat"), ("name", "Nama")))
    limit = forms.IntegerField(required=False, min_value=1, max_value=200)

    def clean(self):
        cleaned = super().clean()
        has_lat = cleaned.get("lat") is not None
        has_lng = cleaned.get("lng") is not None
        if has_lat != has_lng and "lat" not in self.errors and "lng" not in self.errors:
            self.add_error("lat" if not has_lat else "lng", "Isi lat dan lng bersamaan.")
        return cleaned

    @property
    def origin(self):
        lat, lng = self.cleaned_data.get("lat"), self.cleaned_data.get("lng")
        return (lat, lng) if lat is not None and lng is not None else None


def _active_points():
    return CollectionPoint.objects.filter(
        is_active=True, latitude__isnull=False, longitude__isnull=False
    )


def _too_many_requests():
    return JsonResponse(
        {"error": "Terlalu banyak permintaan. Coba lagi dalam 1 menit."},
        status=429,
        headers={"Retry-After": "60"},
    )


def find_points(params):
    """Filter, measure, and sort active points. Returns (results, categories, origin)."""
    form = params
    origin = form.origin
    query = form.cleaned_data.get("q", "").strip()
    points = _active_points()
    if query:
        points = points.filter(name__icontains=query) | points.filter(address__icontains=query)

    now = timezone.localtime()
    rows = [services.serialize_point(point, now, origin) for point in points]
    radius = form.cleaned_data.get("radius")
    if origin and radius:
        rows = [row for row in rows if row["distance_km"] <= radius]
    if form.cleaned_data.get("open_now"):
        rows = [row for row in rows if row["is_open"]]

    counts = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    categories = [
        {"value": value, "label": services.category_label(value), "count": count}
        for value, count in sorted(counts.items(), key=lambda item: -item[1])
    ]

    category = form.cleaned_data.get("category")
    if category:
        rows = [row for row in rows if row["category"] == category]

    sort = form.cleaned_data.get("sort") or ("nearest" if origin else "name")
    if sort == "nearest" and origin:
        rows.sort(key=lambda row: row["distance_km"])
    else:
        rows.sort(key=lambda row: row["name"].lower())
    return rows, categories, origin


@require_GET
def api_points(request):
    """GET /location/api/points/?q=&lat=&lng=&radius=&category=&open_now=1&sort=&limit="""
    form = PointQueryForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    rows, categories, origin = find_points(form)
    limit = form.cleaned_data.get("limit")
    return JsonResponse({
        "count": len(rows),
        "origin": {"latitude": origin[0], "longitude": origin[1]} if origin else None,
        "categories": categories,
        "results": rows[:limit] if limit else rows,
    })


@require_GET
def api_point_detail(request, point_id):
    form = PointQueryForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    point = _active_points().filter(pk=point_id).first()
    if point is None:
        raise Http404
    return JsonResponse(services.serialize_point(point, timezone.localtime(), form.origin))


@require_GET
def api_point_address(request, point_id):
    """The stored address, or one looked up on OpenStreetMap when it is missing."""
    point = _active_points().filter(pk=point_id).first()
    if point is None:
        raise Http404
    if point.address and point.address != services.PLACEHOLDER_ADDRESS:
        return JsonResponse({"address": point.address, "source": "database"})
    if services.throttle(request, "address", ADDRESS_LIMIT_PER_MINUTE):
        return _too_many_requests()
    try:
        address = services.reverse_geocode(float(point.latitude), float(point.longitude))
    except services.GeocodingError:
        return JsonResponse({"error": "Alamat tidak dapat dimuat dari OpenStreetMap."}, status=502)
    return JsonResponse({"address": address, "source": "openstreetmap"})


@require_GET
def api_geocode(request):
    """GET /location/api/geocode/?q= — find a place in Indonesia (OpenStreetMap)."""
    query = request.GET.get("q", "").strip()
    if len(query) < 3 or len(query) > 120:
        return JsonResponse({"error": "Kata kunci minimal 3 karakter."}, status=400)
    if services.throttle(request, "geocode", GEOCODE_LIMIT_PER_MINUTE):
        return _too_many_requests()
    try:
        results = services.geocode(query)
    except services.GeocodingError:
        return JsonResponse({"error": "Pencarian lokasi sedang tidak tersedia. Coba lagi nanti."}, status=502)
    return JsonResponse({"results": results})


def location_list(request):
    form = PointQueryForm({})
    form.is_valid()
    rows, categories, _ = find_points(form)
    return render(request, "location/index.html", {
        "active_item": "location",
        "points": rows,
        "categories": categories,
    })
