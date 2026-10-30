from decimal import Decimal
from unittest import mock

import requests
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from waste.models import CollectionPoint

POINTS_URL = reverse("location:api_points")
GEOCODE_URL = reverse("location:api_geocode")


def point_url(point):
    return reverse("location:api_point_detail", args=[point.pk])


def address_url(point):
    return reverse("location:api_point_address", args=[point.pk])


class LocationApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        # The seed migration adds real points; start every test from a known set.
        CollectionPoint.objects.all().delete()
        self.monas = self.make_point("UPS Monas", -6.175400, 106.827200, hours="Senin - Minggu, 00.00 - 23.59 WIB")
        self.hi = self.make_point("Bank Sampah Bundaran HI", -6.195000, 106.823100, address="Jl. MH Thamrin No. 1")
        self.depok = self.make_point("TPA Cipayung", -6.419047, 106.787003)
        self.closed = self.make_point("TPS Inactive", -6.2, 106.8, is_active=False)

    def make_point(self, name, lat, lng, address="Alamat belum tersedia", hours="", is_active=True):
        return CollectionPoint.objects.create(
            name=name, address=address, operating_hours=hours,
            latitude=Decimal(str(lat)), longitude=Decimal(str(lng)), is_active=is_active,
        )

    def get_points(self, **params):
        response = self.client.get(POINTS_URL, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class PointListApiTests(LocationApiTestCase):
    def test_lists_active_points_with_public_fields(self):
        data = self.get_points()

        self.assertEqual(data["count"], 3)
        first = data["results"][0]
        for field in ("id", "name", "address", "latitude", "longitude", "operating_hours",
                      "is_open", "opening_label", "category", "category_label", "distance_km", "directions_url"):
            self.assertIn(field, first)
        self.assertNotIn("TPS Inactive", [row["name"] for row in data["results"]])

    def test_sorts_by_distance_from_given_origin_and_reports_it(self):
        data = self.get_points(lat="-6.1760", lng="106.8270")

        self.assertEqual([row["name"] for row in data["results"]], ["UPS Monas", "Bank Sampah Bundaran HI", "TPA Cipayung"])
        self.assertLess(data["results"][0]["distance_km"], 0.2)
        self.assertEqual(data["origin"], {"latitude": -6.176, "longitude": 106.827})

    def test_radius_filter_needs_an_origin(self):
        near = self.get_points(lat="-6.1760", lng="106.8270", radius="5")

        self.assertEqual(near["count"], 2)
        self.assertEqual(self.get_points(radius="5")["count"], 3)

    def test_search_matches_name_or_address_case_insensitively(self):
        self.assertEqual([row["name"] for row in self.get_points(q="thamrin")["results"]], ["Bank Sampah Bundaran HI"])
        self.assertEqual([row["name"] for row in self.get_points(q="monas")["results"]], ["UPS Monas"])

    def test_filters_by_category_and_reports_category_counts(self):
        data = self.get_points(category="tpa")

        self.assertEqual([row["name"] for row in data["results"]], ["TPA Cipayung"])
        counts = {row["value"]: row["count"] for row in data["categories"]}
        self.assertEqual(counts, {"ups": 1, "bank_sampah": 1, "tpa": 1})

    def test_open_now_keeps_only_points_known_to_be_open(self):
        data = self.get_points(open_now="1")

        self.assertEqual([row["name"] for row in data["results"]], ["UPS Monas"])

    def test_sort_by_name_and_limit(self):
        data = self.get_points(sort="name", limit="2")

        self.assertEqual([row["name"] for row in data["results"]], ["Bank Sampah Bundaran HI", "TPA Cipayung"])
        self.assertEqual(data["count"], 3)

    def test_invalid_parameters_answer_400_with_field_errors(self):
        response = self.client.get(POINTS_URL, {"lat": "abc", "lng": "106.8", "radius": "-1", "sort": "random"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"lat", "radius", "sort"})

    def test_half_an_origin_is_rejected(self):
        response = self.client.get(POINTS_URL, {"lat": "-6.2"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("lng", response.json()["errors"])

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post(POINTS_URL).status_code, 405)

    def test_query_count_is_constant(self):
        with self.assertNumQueries(1):
            self.client.get(POINTS_URL, {"lat": "-6.2", "lng": "106.8"})


class PointDetailApiTests(LocationApiTestCase):
    def test_returns_one_active_point_with_distance(self):
        data = self.client.get(point_url(self.hi), {"lat": "-6.1754", "lng": "106.8272"}).json()

        self.assertEqual(data["name"], "Bank Sampah Bundaran HI")
        self.assertAlmostEqual(data["distance_km"], 2.2, delta=0.2)
        self.assertIn("openstreetmap.org/directions", data["directions_url"])

    def test_inactive_or_missing_points_are_404(self):
        self.assertEqual(self.client.get(point_url(self.closed)).status_code, 404)
        self.assertEqual(self.client.get(reverse("location:api_point_detail", args=[999999])).status_code, 404)


def fake_response(payload, status=200):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(f"{status}")
    return response


class GeocodeApiTests(LocationApiTestCase):
    @mock.patch("location.services.requests.get")
    def test_proxies_nominatim_search_and_caches_it(self, get):
        get.return_value = fake_response([
            {"display_name": "Tebet, Jakarta Selatan, Indonesia", "lat": "-6.2260", "lon": "106.8530"},
        ])

        first = self.client.get(GEOCODE_URL, {"q": "Tebet"}).json()
        self.client.get(GEOCODE_URL, {"q": "tebet "})

        self.assertEqual(first["results"], [{"label": "Tebet, Jakarta Selatan", "latitude": -6.226, "longitude": 106.853}])
        self.assertEqual(get.call_count, 1)
        _, kwargs = get.call_args
        self.assertEqual(kwargs["params"]["countrycodes"], "id")
        self.assertIn("SiLoak", kwargs["headers"]["User-Agent"])

    def test_short_queries_are_rejected_without_calling_upstream(self):
        with mock.patch("location.services.requests.get") as get:
            response = self.client.get(GEOCODE_URL, {"q": "ab"})

        self.assertEqual(response.status_code, 400)
        get.assert_not_called()

    @mock.patch("location.services.requests.get", side_effect=requests.Timeout("slow"))
    def test_upstream_failure_answers_502_with_a_message(self, _get):
        response = self.client.get(GEOCODE_URL, {"q": "Depok"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())

    @mock.patch("location.services.requests.get")
    def test_geocoding_is_throttled_per_client(self, get):
        get.return_value = fake_response([])
        codes = [self.client.get(GEOCODE_URL, {"q": f"tempat {i}"}).status_code for i in range(11)]

        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10], 429)


class PointAddressApiTests(LocationApiTestCase):
    @mock.patch("location.services.requests.get")
    def test_missing_address_is_filled_by_reverse_geocoding(self, get):
        get.return_value = fake_response({"display_name": "Jl. Merdeka, Gambir, Jakarta Pusat, Indonesia"})

        data = self.client.get(address_url(self.monas)).json()
        self.client.get(address_url(self.monas))

        self.assertEqual(data, {"address": "Jl. Merdeka, Gambir, Jakarta Pusat", "source": "openstreetmap"})
        self.assertEqual(get.call_count, 1)

    def test_stored_address_is_returned_without_calling_upstream(self):
        with mock.patch("location.services.requests.get") as get:
            data = self.client.get(address_url(self.hi)).json()

        self.assertEqual(data, {"address": "Jl. MH Thamrin No. 1", "source": "database"})
        get.assert_not_called()

    @mock.patch("location.services.requests.get", side_effect=requests.ConnectionError("down"))
    def test_reverse_geocoding_failure_answers_502(self, _get):
        self.assertEqual(self.client.get(address_url(self.monas)).status_code, 502)
