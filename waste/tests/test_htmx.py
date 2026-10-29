import json

from django.urls import reverse

from pickup.models import PickupRequest
from waste.models import Submission

from .test_history import HistoryTestCase

HX = {"HTTP_HX_REQUEST": "true"}
CANCEL_ENTRY_URL = reverse("waste:cancel_entry")
PickupStatus = PickupRequest.Status


def toast(response):
    return json.loads(response["HX-Trigger"])["showToast"]


class CancelEntryTests(HistoryTestCase):
    def test_htmx_cancel_of_a_dropoff_returns_the_updated_row_and_stats(self):
        submission = self.make_submission()
        response = self.client.post(CANCEL_ENTRY_URL, {"entry": f"dropoff:{submission.pk}"}, **HX)

        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.CANCELED)
        self.assertTemplateUsed(response, "waste/partials/history_row.html")
        self.assertContains(response, f'id="entry-dropoff-{submission.pk}"')
        self.assertContains(response, 'id="history-stats"')
        self.assertEqual(toast(response)["level"], "success")

    def test_htmx_cancel_of_a_pickup_logs_the_status_change(self):
        pickup = self.make_pickup()
        response = self.client.post(CANCEL_ENTRY_URL, {"entry": f"pickup:{pickup.pk}"}, **HX)

        pickup.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pickup.status, PickupStatus.CANCELLED)
        self.assertTrue(pickup.status_history.filter(new_status=PickupStatus.CANCELLED).exists())

    def test_entry_that_can_no_longer_be_cancelled_answers_409(self):
        submission = self.make_submission(status=Submission.Status.VERIFIED)
        response = self.client.post(CANCEL_ENTRY_URL, {"entry": f"dropoff:{submission.pk}"}, **HX)

        self.assertEqual(response.status_code, 409)
        self.assertIn("tidak dapat dibatalkan", response.content.decode())

    def test_other_users_entries_and_garbage_are_not_found(self):
        foreign = self.make_submission(user=self.other_giver)
        for entry in (f"dropoff:{foreign.pk}", "pickup:not-a-uuid", "nothing"):
            self.assertEqual(self.client.post(CANCEL_ENTRY_URL, {"entry": entry}, **HX).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, Submission.Status.PENDING)

    def test_without_htmx_it_redirects_back_to_history(self):
        submission = self.make_submission()
        response = self.client.post(CANCEL_ENTRY_URL, {"entry": f"dropoff:{submission.pk}"})

        self.assertRedirects(response, reverse("waste:submissions"), fetch_redirect_response=False)

    def test_history_rows_offer_an_optimistic_cancel_button(self):
        self.make_submission()
        response = self.client.get(reverse("waste:submissions"))

        self.assertContains(response, "data-optimistic-cancel")
        self.assertContains(response, 'hx-post="%s"' % CANCEL_ENTRY_URL)


class SetorFormHtmxTests(HistoryTestCase):
    def dropoff_payload(self, **overrides):
        data = {
            "delivery_method": "antar_sendiri",
            "collection_point": str(self.point.pk),
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "6",
            "items-0-waste_type": str(self.waste_type.pk),
            "items-0-estimated_weight": "2.50",
            "incentive_allocation": "wallet",
        }
        data.update(overrides)
        return data

    def test_valid_htmx_submission_navigates_to_the_detail_without_reload(self):
        response = self.client.post(reverse("waste:new"), self.dropoff_payload(), **HX)

        submission = Submission.objects.get(user=self.giver)
        location = json.loads(response["HX-Location"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(location["path"], reverse("waste:detail", args=[submission.pk]))
        self.assertEqual(location["target"], "#page-root")

    def test_invalid_htmx_submission_returns_422_with_the_form_and_errors(self):
        response = self.client.post(reverse("waste:new"), self.dropoff_payload(**{"items-0-estimated_weight": "0"}), **HX)

        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'id="setor-root"', status_code=422)
        self.assertFalse(Submission.objects.exists())

    def test_htmx_pickup_request_navigates_to_the_pickup_detail(self):
        response = self.client.post(reverse("waste:new"), self.pickup_payload(), **HX)

        pickup = PickupRequest.objects.get(giver=self.giver)
        self.assertEqual(json.loads(response["HX-Location"])["path"], reverse("pickup:show_pickup_detail", args=[pickup.pk]))

    def test_plain_post_still_works_without_javascript(self):
        response = self.client.post(reverse("waste:new"), self.dropoff_payload())

        submission = Submission.objects.get(user=self.giver)
        self.assertRedirects(response, reverse("waste:detail", args=[submission.pk]))

    def test_form_page_loads_the_setor_module_instead_of_inline_script(self):
        response = self.client.get(reverse("waste:new"))

        self.assertContains(response, "js/siloak/setor-form.js")
        self.assertContains(response, 'hx-post="%s"' % reverse("waste:new"))
        self.assertNotContains(response, "function selectPoint")


class DetailCancelHtmxTests(HistoryTestCase):
    def test_htmx_cancel_on_detail_returns_the_refreshed_detail(self):
        submission = self.make_submission()
        response = self.client.post(reverse("waste:cancel", args=[submission.pk]), **HX)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "waste/detail.html")
        self.assertContains(response, "Dibatalkan")
        self.assertEqual(toast(response)["level"], "success")

    def test_htmx_cancel_of_locked_submission_answers_409(self):
        submission = self.make_submission(status=Submission.Status.VERIFIED)
        response = self.client.post(reverse("waste:cancel", args=[submission.pk]), **HX)

        self.assertEqual(response.status_code, 409)
