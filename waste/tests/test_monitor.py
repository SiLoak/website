from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from pickup.models import PickupRequest, PickupStatusHistory
from waste.models import Submission
from wallet.services import credit_wallet

from .test_history import HistoryTestCase

MONITOR_URL = reverse("waste:monitor")
PickupStatus = PickupRequest.Status


class MonitorTestCase(HistoryTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def age_pickup(self, pickup, hours):
        PickupRequest.objects.filter(pk=pickup.pk).update(created_at=timezone.now() - timedelta(hours=hours))


class MonitorAccessTests(MonitorTestCase):
    def test_staff_only(self):
        self.client.force_login(self.giver)
        self.assertEqual(self.client.get(MONITOR_URL).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(MONITOR_URL).status_code, 302)

    def test_navbar_shows_monitor_link_to_staff_only(self):
        self.assertContains(self.client.get(reverse("waste:submissions")), MONITOR_URL)
        self.client.force_login(self.giver)
        self.assertNotContains(self.client.get(reverse("waste:submissions")), MONITOR_URL)


class MonitorSummaryTests(MonitorTestCase):
    def test_summary_counts_operational_numbers(self):
        self.make_pickup()
        self.make_pickup(status=PickupStatus.ON_THE_WAY)
        self.make_pickup(status=PickupStatus.CANCELLED)
        self.make_submission()
        verified = self.make_submission(status=Submission.Status.VERIFIED)
        verified.items.update(actual_weight=Decimal("4.00"))
        self.make_pickup(status=PickupStatus.COMPLETED, actual_weight="1.50")
        credit_wallet(self.giver, Decimal("12000"), "Insentif uji", reference="uji:1")

        summary = self.client.get(MONITOR_URL).context["summary"]

        self.assertEqual(summary["pickups_waiting"], 1)
        self.assertEqual(summary["pickups_active"], 2)
        self.assertEqual(summary["dropoffs_pending"], 1)
        self.assertEqual(summary["weight_30d"], Decimal("5.50"))
        self.assertEqual(summary["incentive_30d"], Decimal("12000"))
        self.assertEqual(summary["new_today"], 6)

    def test_status_breakdown_lists_every_pickup_status(self):
        self.make_pickup()
        self.make_pickup()
        self.make_pickup(status=PickupStatus.FAILED)

        breakdown = {row["status"]: row["count"] for row in self.client.get(MONITOR_URL).context["pickup_breakdown"]}

        self.assertEqual(breakdown[PickupStatus.PENDING], 2)
        self.assertEqual(breakdown[PickupStatus.FAILED], 1)
        self.assertEqual(breakdown[PickupStatus.COMPLETED], 0)


class MonitorAttentionTests(MonitorTestCase):
    def test_flags_stale_unassigned_pickups_and_old_pending_dropoffs(self):
        stale = self.make_pickup()
        self.age_pickup(stale, hours=30)
        self.make_pickup()
        old_dropoff = self.make_submission(days_ago=4)
        self.make_submission(days_ago=1)

        attention = self.client.get(MONITOR_URL).context["attention"]

        self.assertEqual([item["pk"] for item in attention["pickups"]], [stale.pk])
        self.assertEqual([item["pk"] for item in attention["dropoffs"]], [old_dropoff.pk])


class MonitorFeedTests(MonitorTestCase):
    def test_feed_merges_pickup_history_and_dropoffs_newest_first(self):
        dropoff = self.make_submission(days_ago=1)
        pickup = self.make_pickup()

        feed = self.client.get(MONITOR_URL).context["feed"]

        self.assertEqual([(item["kind"], item["pk"]) for item in feed[:2]], [("pickup", pickup.pk), ("dropoff", dropoff.pk)])
        self.assertTrue(all(item["url"] for item in feed))

    def test_feed_can_be_filtered_by_kind(self):
        self.make_submission()
        self.make_pickup()

        feed = self.client.get(MONITOR_URL, {"kind": "dropoff"}).context["feed"]

        self.assertEqual({item["kind"] for item in feed}, {"dropoff"})

    def test_feed_is_capped(self):
        pickup = self.make_pickup()
        PickupStatusHistory.objects.bulk_create([
            PickupStatusHistory(pickup=pickup, new_status=PickupStatus.PENDING) for _ in range(30)
        ])

        self.assertEqual(len(self.client.get(MONITOR_URL).context["feed"]), 20)

    def test_htmx_polling_returns_only_the_feed_partial(self):
        self.make_pickup()
        response = self.client.get(MONITOR_URL, {"kind": "pickup"}, HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "waste/partials/monitor_feed.html")
        self.assertTemplateNotUsed(response, "waste/monitor.html")

    def test_page_polls_the_feed_with_htmx(self):
        self.assertContains(self.client.get(MONITOR_URL), 'hx-trigger="every 30s')

    def test_query_count_does_not_grow_with_activity(self):
        self.make_pickup()
        self.make_submission()
        with CaptureQueriesContext(connection) as few:
            self.client.get(MONITOR_URL)
        for _ in range(6):
            self.make_pickup()
            self.make_submission()
        with CaptureQueriesContext(connection) as many:
            self.client.get(MONITOR_URL)

        self.assertEqual(len(few), len(many))
