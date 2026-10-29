import json

from django.urls import reverse

from .helpers import PickupTestCase, Status

HX = {"HTTP_HX_REQUEST": "true"}


class PickupDetailHtmxTests(PickupTestCase):
    def detail(self, pickup):
        return reverse("pickup:show_pickup_detail", args=[pickup.pk])

    def test_giver_cancel_via_htmx_returns_the_refreshed_detail_and_toast(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.post(reverse("pickup:cancel_pickup_ajax", args=[pickup.pk]), **HX)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pickup/detail.html")
        self.assertEqual(json.loads(response["HX-Trigger"])["showToast"]["level"], "success")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.CANCELLED)

    def test_json_clients_still_get_json(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.post(reverse("pickup:cancel_pickup_ajax", args=[pickup.pk]))

        self.assertEqual(response.json()["status"], Status.CANCELLED)

    def test_collector_status_update_via_htmx(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)
        response = self.client.post(
            reverse("pickup:update_pickup_status_ajax", args=[pickup.pk]), {"status": Status.ON_THE_WAY}, **HX
        )

        self.assertTemplateUsed(response, "pickup/detail.html")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ON_THE_WAY)

    def test_invalid_weighing_via_htmx_returns_422_with_field_errors(self):
        pickup = self.make_pickup(status=Status.WEIGHING)
        item = pickup.items.get()
        self.client.force_login(self.collector)
        response = self.client.post(reverse("pickup:complete_weighing_ajax", args=[pickup.pk]), {
            "weigh-TOTAL_FORMS": "1", "weigh-INITIAL_FORMS": "1",
            "weigh-0-id": str(item.pk), "weigh-0-actual_weight": "",
        }, **HX)

        self.assertEqual(response.status_code, 422)
        self.assertTemplateUsed(response, "pickup/detail.html")
        self.assertTrue(response.context["weighing_formset"].errors[0])

    def test_valid_weighing_via_htmx_completes_and_credits(self):
        pickup = self.make_pickup(status=Status.WEIGHING)
        item = pickup.items.get()
        self.client.force_login(self.collector)
        response = self.client.post(reverse("pickup:complete_weighing_ajax", args=[pickup.pk]), {
            "weigh-TOTAL_FORMS": "1", "weigh-INITIAL_FORMS": "1",
            "weigh-0-id": str(item.pk), "weigh-0-actual_weight": "3.00",
        }, **HX)

        self.assertEqual(response.status_code, 200)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.COMPLETED)

    def test_detail_page_uses_htmx_attributes_and_the_detail_module(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.get(self.detail(pickup))

        self.assertContains(response, 'hx-post="%s"' % reverse("pickup:cancel_pickup_ajax", args=[pickup.pk]))
        self.assertNotContains(response, "async function postData")
