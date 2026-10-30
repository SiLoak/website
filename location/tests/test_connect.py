"""The location module feeding the maps in other modules (landing, setor form)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from waste.models import CollectionPoint

from .test_api import fake_response

REVERSE_URL = reverse("location:api_reverse")


class ConnectTestCase(TestCase):
    def setUp(self):
        cache.clear()
        CollectionPoint.objects.all().delete()
        self.with_hours = CollectionPoint.objects.create(
            name="Bank Sampah Jam Lengkap", address="Jl. Lengkap 1",
            operating_hours="Senin - Minggu, 00.00 - 23.59 WIB", latitude="-6.2", longitude="106.8",
        )
        self.without_hours = CollectionPoint.objects.create(
            name="UPS Tanpa Jam", address="Alamat belum tersedia", latitude="-6.3", longitude="106.9",
        )


class OpeningHoursDisplayTests(ConnectTestCase):
    def test_location_cards_show_hours_only_when_known(self):
        response = self.client.get(reverse("location:list"))
        html = response.content.decode()
        known_card = html.split("Bank Sampah Jam Lengkap")[1].split("</article>")[0]
        unknown_card = html.split("UPS Tanpa Jam")[1].split("</article>")[0]

        self.assertIn("Buka sampai", known_card)
        self.assertNotIn("Jam belum tersedia", unknown_card)
        self.assertNotIn("Jam ?", unknown_card)

    def test_setor_ke_sini_preselects_the_point_in_the_setor_form(self):
        response = self.client.get(reverse("location:list"))

        self.assertContains(response, reverse("waste:new") + f"?point={self.with_hours.pk}")


class PointInfoFilterTests(ConnectTestCase):
    def render(self, point):
        return Template("{% load location_tags %}{% with info=point|point_info %}"
                        "{{ info.category_label }}|{{ info.address }}|{{ info.is_open }}|{{ info.opening_label }}"
                        "{% endwith %}").render(Context({"point": point}))

    def test_point_info_gives_category_hours_and_clean_address(self):
        self.assertEqual(self.render(self.with_hours), "Bank sampah|Jl. Lengkap 1|True|Buka sampai 23.59")
        self.assertEqual(self.render(self.without_hours), "Unit pengolahan sampah||None|")


class ReverseApiTests(ConnectTestCase):
    @mock.patch("location.services.requests.get")
    def test_reverse_geocodes_any_coordinate(self, get):
        get.return_value = fake_response({"display_name": "Jl. Melati, Tebet, Jakarta Selatan, Indonesia"})

        data = self.client.get(REVERSE_URL, {"lat": "-6.226", "lng": "106.853"}).json()

        self.assertEqual(data, {"address": "Jl. Melati, Tebet, Jakarta Selatan"})

    def test_reverse_rejects_bad_coordinates(self):
        self.assertEqual(self.client.get(REVERSE_URL, {"lat": "x", "lng": "106"}).status_code, 400)
        self.assertEqual(self.client.get(REVERSE_URL, {"lat": "-6.2"}).status_code, 400)


class LandingMapTests(ConnectTestCase):
    def test_landing_lists_real_points_and_links_to_the_location_page(self):
        response = self.client.get(reverse("landing_page"))

        self.assertContains(response, "Bank Sampah Jam Lengkap")
        self.assertNotContains(response, "TPST SiLoak Tebet Timur")
        self.assertContains(response, 'action="%s"' % reverse("location:list"))
        self.assertContains(response, 'name="q"')
        self.assertContains(response, reverse("location:list"))

    def test_landing_map_uses_the_location_payload(self):
        response = self.client.get(reverse("landing_page"))
        names = {point["name"] for point in response.context["map_points"]}

        self.assertEqual(names, {"Bank Sampah Jam Lengkap", "UPS Tanpa Jam"})
        self.assertIn("category_label", response.context["map_points"][0])


class SetorFormMapTests(ConnectTestCase):
    def setUp(self):
        super().setUp()
        user = get_user_model().objects.create_user("map-giver", password="unused-test-pass")
        self.client.force_login(user)

    def test_setor_form_loads_the_location_connector_with_api_urls(self):
        response = self.client.get(reverse("waste:new"))

        self.assertContains(response, "js/location-connect.js")
        self.assertContains(response, 'data-geocode-url="%s"' % reverse("location:api_geocode"))
        self.assertContains(response, 'data-reverse-url="%s"' % REVERSE_URL)

    def test_pickup_search_and_use_my_location_are_enabled(self):
        html = self.client.get(reverse("waste:new")).content.decode()
        pickup_section = html.split('id="pickup-address-heading"')[1].split("</section>")[0]

        self.assertIn('id="pickup-address-search"', pickup_section)
        self.assertIn("data-pickup-use-location", pickup_section)
        self.assertNotIn("disabled", pickup_section.split("pickup-preview-map")[0])

    def test_point_cards_only_claim_open_when_hours_are_known(self):
        html = self.client.get(reverse("waste:new")).content.decode()
        unknown_card = html.split('data-point-name="UPS Tanpa Jam"')[1].split("</button>")[0]
        known_card = html.split('data-point-name="Bank Sampah Jam Lengkap"')[1].split("</button>")[0]

        self.assertNotIn(">Buka<", unknown_card)
        self.assertIn(">Buka<", known_card)
        self.assertIn("Unit pengolahan sampah", unknown_card)


class LandingInteractiveTests(ConnectTestCase):
    def html(self):
        return self.client.get(reverse("landing_page")).content.decode()

    def test_landing_loads_the_interactive_finder_wired_to_the_api(self):
        html = self.html()

        self.assertIn("js/location-landing.js", html)
        self.assertIn('data-points-url="%s"' % reverse("location:api_points"), html)
        self.assertIn('data-geocode-url="%s"' % reverse("location:api_geocode"), html)
        self.assertIn('id="landing-point-template"', html)

    def test_cards_and_controls_carry_hooks_for_the_map(self):
        html = self.html()

        self.assertIn(f'data-landing-card data-point-id="{self.with_hours.pk}"', html)
        for km in ("2", "5", "10"):
            self.assertIn(f'data-landing-radius="{km}"', html)
        self.assertIn("data-landing-nearest", html)
        # The location module handles "Cari yang terdekat" now, not the generic map helper.
        self.assertNotIn('data-find-nearest="landing-map"', html)
