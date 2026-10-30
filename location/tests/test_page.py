from django.test import TestCase
from django.urls import reverse

from waste.models import CollectionPoint


class LocationPageTests(TestCase):
    def setUp(self):
        CollectionPoint.objects.all().delete()
        CollectionPoint.objects.create(name="UPS Uji", address="Jl. Uji 1", latitude="-6.2", longitude="106.8")

    def test_page_renders_real_points_instead_of_placeholder_cards(self):
        response = self.client.get(reverse("location:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UPS Uji")
        self.assertNotContains(response, "Titik Pengumpulan Cilandak")
        self.assertNotContains(response, "5 Lokasi Aktif di Sekitarmu")

    def test_page_wires_the_api_and_page_script(self):
        response = self.client.get(reverse("location:list"))

        self.assertContains(response, 'data-points-url="%s"' % reverse("location:api_points"))
        self.assertContains(response, 'data-geocode-url="%s"' % reverse("location:api_geocode"))
        self.assertContains(response, "js/location-page.js")
        self.assertContains(response, "css/location.css")

    def test_category_filter_lists_service_types_present_in_the_data(self):
        response = self.client.get(reverse("location:list"))

        self.assertContains(response, 'value="ups"')
