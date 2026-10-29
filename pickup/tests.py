from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from pickup.models import PickupItem, PickupRequest
from wallet.models import Donation, WalletTransaction
from waste.models import Submission, WasteType


class PickupIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.giver = User.objects.create_user(
            username="giver", email="giver@example.com", password="secret"
        )
        self.collector = User.objects.create_user(
            username="collector", email="collector@example.com", password="secret"
        )
        Group.objects.get_or_create(name="Giver")[0].user_set.add(self.giver)
        Group.objects.get_or_create(name="Collector")[0].user_set.add(self.collector)
        self.waste_type = WasteType.objects.create(
            name="Botol PET", rate_per_kg=Decimal("8000.00")
        )

    def make_pickup(self, *, status=PickupRequest.Status.PENDING, verified_at=None):
        pickup = PickupRequest.objects.create(
            giver=self.giver,
            collector=self.collector if status != PickupRequest.Status.PENDING else None,
            pickup_address="Jl. Mawar No. 12, Pasar Minggu",
            scheduled_date=date.today(),
            time_slot=PickupRequest.TimeSlot.S0810,
            status=status,
            verified_at=verified_at,
        )
        item = PickupItem.objects.create(
            pickup_request=pickup,
            waste_type=self.waste_type,
            estimated_weight=Decimal("2.00"),
            actual_weight=Decimal("1.75") if status == PickupRequest.Status.COMPLETED else None,
            unit_rate_snapshot=self.waste_type.rate_per_kg,
        )
        return pickup, item

    def test_giver_pickup_entry_opens_shared_form_with_pickup_selected(self):
        self.client.force_login(self.giver)

        response = self.client.get(reverse("pickup:show_pickup_list"))

        self.assertRedirects(
            response,
            f"{reverse('waste:new')}?delivery_method=minta_dijemput",
        )
        form_page = self.client.get(response.url)
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, 'value="minta_dijemput" data-delivery-mode checked')

    def test_combined_history_and_waste_history_route_include_pickups(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.giver)

        response = self.client.get(reverse("waste:submissions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Minta dijemput")
        self.assertContains(
            response,
            reverse("pickup:show_pickup_detail", kwargs={"pickup_id": pickup.pk}),
        )
        self.assertRedirects(
            self.client.get(reverse("history")),
            reverse("waste:submissions"),
        )

    def test_giver_dashboard_links_to_real_pickup_and_recent_activity(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.giver)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Pickup #{str(pickup.pk)[:8]}")
        self.assertContains(
            response,
            reverse("pickup:show_pickup_detail", kwargs={"pickup_id": pickup.pk}),
        )
        self.assertNotContains(response, "Pickup #8821")

    def test_profile_activity_includes_pickup(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.giver)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pickup_count"], 1)
        self.assertContains(response, f"Pickup #{str(pickup.pk)[:8]}")
        self.assertContains(
            response,
            reverse("pickup:show_pickup_detail", kwargs={"pickup_id": pickup.pk}),
        )

    def test_collector_dashboard_and_task_history_are_accessible(self):
        pickup, _ = self.make_pickup(status=PickupRequest.Status.ASSIGNED)
        available, _ = self.make_pickup()
        self.client.force_login(self.collector)

        self.assertRedirects(
            self.client.get(reverse("dashboard")),
            reverse("pickup:show_collector_pickup_list"),
        )
        dashboard = self.client.get(reverse("pickup:show_collector_pickup_list"))
        self.assertEqual(dashboard.status_code, 200)

        api = self.client.get(reverse("pickup:get_collector_pickup_json"))
        self.assertEqual(api.status_code, 200)
        data = api.json()[0]["fields"]
        self.assertEqual(data["pickup_address"], pickup.pickup_address)
        self.assertEqual(data["status"], PickupRequest.Status.ASSIGNED)
        self.assertEqual(data["items"], [self.waste_type.name])
        assigned_response = self.client.get(
            reverse("pickup:get_collector_pickup_json"), {"scope": "mine"}
        )
        self.assertEqual(assigned_response.json()[0]["pk"], str(pickup.pk))
        available_response = self.client.get(
            reverse("pickup:get_collector_pickup_json"), {"scope": "available"}
        )
        self.assertEqual(available_response.json()[0]["pk"], str(available.pk))

        history = self.client.get(reverse("pickup:show_collector_pickup_history"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, str(pickup.pk))

    def test_admin_verification_releases_pickup_incentive_once(self):
        staff = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="secret"
        )
        pickup, _ = self.make_pickup(status=PickupRequest.Status.COMPLETED)
        self.client.force_login(staff)
        changelist = reverse("admin:pickup_pickuprequest_changelist")

        response = self.client.post(
            changelist,
            {
                "action": "verify_pickups",
                "index": "0",
                "_selected_action": [str(pickup.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        pickup.refresh_from_db()
        self.assertIsNotNone(pickup.verified_at)
        self.assertEqual(pickup.verified_by, staff)
        self.assertEqual(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").count(), 1)

        self.client.post(
            reverse("admin:pickup_pickuprequest_changelist"),
            {
                "action": "verify_pickups",
                "index": "0",
                "_selected_action": [str(pickup.pk)],
            },
        )
        self.assertEqual(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").count(), 1)

    def test_admin_verification_uses_current_rate_for_unpriced_snapshot(self):
        staff = get_user_model().objects.create_superuser(
            username="rate-admin", email="rate-admin@example.com", password="secret"
        )
        pickup, item = self.make_pickup(status=PickupRequest.Status.COMPLETED)
        item.unit_rate_snapshot = None
        item.save(update_fields=["unit_rate_snapshot"])
        self.client.force_login(staff)

        self.client.post(
            reverse("admin:pickup_pickuprequest_changelist"),
            {
                "action": "verify_pickups",
                "index": "0",
                "_selected_action": [str(pickup.pk)],
            },
        )

        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertIsNotNone(pickup.verified_at)
        self.assertEqual(item.unit_rate_snapshot, self.waste_type.rate_per_kg)

    def test_donation_pickup_is_recorded_on_admin_verification(self):
        staff = get_user_model().objects.create_superuser(
            username="donation-admin", email="donation-admin@example.com", password="secret"
        )
        pickup, _ = self.make_pickup(status=PickupRequest.Status.COMPLETED)
        pickup.incentive_allocation = Submission.IncentiveAllocation.DONATION
        pickup.save(update_fields=["incentive_allocation"])
        self.client.force_login(staff)

        self.client.post(
            reverse("admin:pickup_pickuprequest_changelist"),
            {
                "action": "verify_pickups",
                "index": "0",
                "_selected_action": [str(pickup.pk)],
            },
        )

        self.assertTrue(
            Donation.objects.filter(
                transaction__reference=f"pickup_donation:{pickup.pk}"
            ).exists()
        )
        self.assertTrue(
            pickup.status_history.filter(
                changed_by=staff,
                note="Hasil timbang dan insentif diverifikasi admin.",
            ).exists()
        )

    def test_collector_completion_records_weight_but_waits_for_admin_payout(self):
        pickup, item = self.make_pickup(status=PickupRequest.Status.WEIGHING)
        self.client.force_login(self.collector)

        response = self.client.post(
            reverse("pickup:complete_weighing_ajax", kwargs={"pickup_id": pickup.pk}),
            {
                "weigh-TOTAL_FORMS": "1",
                "weigh-INITIAL_FORMS": "1",
                "weigh-MIN_NUM_FORMS": "0",
                "weigh-MAX_NUM_FORMS": "1000",
                "weigh-0-id": str(item.pk),
                "weigh-0-actual_weight": "1.75",
            },
        )

        self.assertEqual(response.status_code, 200)
        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(pickup.status, PickupRequest.Status.COMPLETED)
        self.assertEqual(item.actual_weight, Decimal("1.75"))
        self.assertIsNone(pickup.verified_at)
        self.assertFalse(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").exists())
