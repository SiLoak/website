from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from pickup.models import PickupRequest
from pickup.tests.helpers import PickupTestCase
from waste.models import CollectionPoint, Submission, SubmissionItem

HISTORY_URL = reverse("waste:submissions")
BULK_CANCEL_URL = reverse("waste:bulk_cancel")
PickupStatus = PickupRequest.Status


class HistoryTestCase(PickupTestCase):
    def setUp(self):
        super().setUp()
        self.point = CollectionPoint.objects.create(name="Depo Uji Tebet", address="Jl. Tebet Raya 1")
        self.client.force_login(self.giver)

    def make_submission(self, *, user=None, status=Submission.Status.PENDING, weight="2.00", waste_type=None, days_ago=0):
        submission = Submission.objects.create(user=user or self.giver, collection_point=self.point, status=status)
        SubmissionItem.objects.create(
            submission=submission,
            waste_type=waste_type or self.waste_type,
            estimated_weight=Decimal(weight),
            unit_rate_snapshot=(waste_type or self.waste_type).rate_per_kg,
        )
        if days_ago:
            Submission.objects.filter(pk=submission.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return submission

    def entries(self, **params):
        response = self.client.get(HISTORY_URL, params)
        self.assertEqual(response.status_code, 200)
        return response, [(entry["kind"], str(entry["pk"])) for entry in response.context["page_obj"]]


class HistoryListTests(HistoryTestCase):
    def test_lists_own_dropoffs_and_pickups_newest_first(self):
        old = self.make_submission(days_ago=3)
        pickup = self.make_pickup()
        self.make_submission(user=self.other_giver)
        self.make_pickup(giver=self.other_giver)

        _, entries = self.entries()

        self.assertEqual(entries, [("pickup", str(pickup.pk)), ("dropoff", str(old.pk))])

    def test_filter_by_type(self):
        dropoff = self.make_submission()
        pickup = self.make_pickup()

        self.assertEqual(self.entries(type="pickup")[1], [("pickup", str(pickup.pk))])
        self.assertEqual(self.entries(type="dropoff")[1], [("dropoff", str(dropoff.pk))])

    def test_filter_by_status_group_spans_both_kinds(self):
        self.make_submission()
        canceled = self.make_submission(status=Submission.Status.CANCELED)
        failed = self.make_pickup(status=PickupStatus.FAILED)
        done = self.make_pickup(status=PickupStatus.COMPLETED)

        _, canceled_entries = self.entries(status="canceled")
        _, done_entries = self.entries(status="done")

        self.assertCountEqual(canceled_entries, [("dropoff", str(canceled.pk)), ("pickup", str(failed.pk))])
        self.assertEqual(done_entries, [("pickup", str(done.pk))])

    def test_search_matches_waste_type_place_and_number(self):
        bottle = self.make_submission(waste_type=self.other_type)
        pickup = self.make_pickup(pickup_address="Jl. Kenanga No. 9, Depok")

        self.assertEqual(self.entries(q="botol")[1], [("dropoff", str(bottle.pk))])
        self.assertEqual(self.entries(q="kenanga")[1], [("pickup", str(pickup.pk))])
        self.assertEqual(self.entries(q=f"#{bottle.pk}")[1], [("dropoff", str(bottle.pk))])
        self.assertEqual(self.entries(q=str(pickup.pk)[:8])[1], [("pickup", str(pickup.pk))])

    def test_filter_by_date_range(self):
        recent = self.make_submission(days_ago=1)
        self.make_submission(days_ago=20)
        date_from = (timezone.localdate() - timedelta(days=7)).isoformat()

        self.assertEqual(self.entries(date_from=date_from)[1], [("dropoff", str(recent.pk))])

    def test_sort_by_heaviest(self):
        light = self.make_submission(weight="1.00")
        heavy = self.make_pickup(weight="9.00")
        middle = self.make_submission(weight="4.00")

        _, entries = self.entries(sort="heaviest")

        self.assertEqual([pk for _, pk in entries], [str(heavy.pk), str(middle.pk), str(light.pk)])

    def test_invalid_filters_are_ignored_with_feedback(self):
        self.make_submission()
        response, entries = self.entries(type="hacker", date_from="not-a-date")

        self.assertEqual(len(entries), 1)
        self.assertTrue(response.context["filter_form"].errors)

    def test_paginates_ten_entries_per_page(self):
        for _ in range(12):
            self.make_submission()

        first_page = self.client.get(HISTORY_URL)
        second_page = self.client.get(HISTORY_URL, {"page": 2})

        self.assertEqual(len(first_page.context["page_obj"]), 10)
        self.assertEqual(len(second_page.context["page_obj"]), 2)

    def test_htmx_requests_receive_only_the_results_partial(self):
        self.make_submission()
        response = self.client.get(HISTORY_URL, {"type": "dropoff"}, HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "waste/partials/history_results.html")
        self.assertTemplateNotUsed(response, "history.html")
        self.assertNotContains(response, "<html")

    def test_summary_counts_use_all_entries_not_the_filtered_page(self):
        verified = self.make_submission(status=Submission.Status.VERIFIED)
        verified.items.update(actual_weight=Decimal("3.00"))
        self.make_pickup(status=PickupStatus.COMPLETED, actual_weight="2.50")
        self.make_pickup()

        response = self.client.get(HISTORY_URL, {"type": "dropoff"})
        stats = response.context["stats"]

        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["done"], 2)
        self.assertEqual(stats["weight"], Decimal("5.50"))

    def test_query_count_does_not_grow_with_the_number_of_entries(self):
        self.make_submission()
        self.make_pickup()
        with CaptureQueriesContext(connection) as few:
            self.client.get(HISTORY_URL)
        for _ in range(8):
            self.make_submission()
            self.make_pickup()
        with CaptureQueriesContext(connection) as many:
            self.client.get(HISTORY_URL)

        self.assertEqual(len(few), len(many))


class BulkCancelTests(HistoryTestCase):
    def test_cancels_selected_pending_entries_of_the_owner(self):
        dropoff = self.make_submission()
        pickup = self.make_pickup()
        response = self.client.post(BULK_CANCEL_URL, {"selected": [f"dropoff:{dropoff.pk}", f"pickup:{pickup.pk}"]})

        self.assertRedirects(response, HISTORY_URL, fetch_redirect_response=False)
        dropoff.refresh_from_db()
        pickup.refresh_from_db()
        self.assertEqual(dropoff.status, Submission.Status.CANCELED)
        self.assertEqual(pickup.status, PickupStatus.CANCELLED)

    def test_skips_entries_that_are_not_cancellable_or_not_owned(self):
        verified = self.make_submission(status=Submission.Status.VERIFIED)
        on_the_way = self.make_pickup(status=PickupStatus.ON_THE_WAY)
        someone_else = self.make_submission(user=self.other_giver)
        response = self.client.post(
            BULK_CANCEL_URL,
            {"selected": [f"dropoff:{verified.pk}", f"pickup:{on_the_way.pk}", f"dropoff:{someone_else.pk}", "pickup:not-a-uuid", "junk"]},
            follow=True,
        )

        for obj in (verified, on_the_way, someone_else):
            obj.refresh_from_db()
        self.assertEqual(verified.status, Submission.Status.VERIFIED)
        self.assertEqual(on_the_way.status, PickupStatus.ON_THE_WAY)
        self.assertEqual(someone_else.status, Submission.Status.PENDING)
        self.assertContains(response, "Tidak ada pengajuan yang dapat dibatalkan")

    def test_htmx_bulk_cancel_returns_refreshed_results(self):
        dropoff = self.make_submission()
        response = self.client.post(BULK_CANCEL_URL, {"selected": [f"dropoff:{dropoff.pk}"]}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "waste/partials/history_results.html")
        self.assertIn("showToast", response["HX-Trigger"])

    def test_bulk_cancel_requires_post_and_login(self):
        self.assertEqual(self.client.get(BULK_CANCEL_URL).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(BULK_CANCEL_URL).status_code, 302)

    def test_bulk_cancel_is_rate_limited(self):
        codes = [self.client.post(BULK_CANCEL_URL, {"selected": []}).status_code for _ in range(6)]

        self.assertEqual(codes[-1], 429)
