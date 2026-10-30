import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.http import Http404
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.test import TestCase, override_settings

from pickup import services
from pickup.models import PickupItem, PickupRequest, PickupStatusHistory
from wallet.models import Donation, WalletTransaction
from waste.models import Submission, WasteType


Status = PickupRequest.Status


TEST_SETTINGS = {
    "SECRET_KEY": "test-only-secret-key-not-for-production",
    "PASSWORD_HASHERS": ["django.contrib.auth.hashers.MD5PasswordHasher"],
}


@override_settings(**TEST_SETTINGS)
class PickupTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.giver = User.objects.create_user(
            username="giver", email="giver@example.com", password="secret"
        )
        self.other_giver = User.objects.create_user(
            username="other-giver", email="other-giver@example.com", password="secret"
        )
        self.collector = User.objects.create_user(
            username="collector", email="collector@example.com", password="secret"
        )
        self.other_collector = User.objects.create_user(
            username="other-collector",
            email="other-collector@example.com",
            password="secret",
        )
        giver_group = Group.objects.get_or_create(name="Giver")[0]
        collector_group = Group.objects.get_or_create(name="Collector")[0]
        for user in (self.giver, self.other_giver):
            user.groups.set([giver_group])
        for user in (self.collector, self.other_collector):
            user.groups.set([collector_group])
        self.waste_type = WasteType.objects.create(
            name="Botol PET", rate_per_kg=Decimal("8000.00")
        )

    def make_pickup(self, *, status=Status.PENDING, verified_at=None, **overrides):
        fields = {
            "giver": self.giver,
            "collector": self.collector if status != Status.PENDING else None,
            "pickup_address": "Jl. Mawar No. 12, Pasar Minggu",
            "address_detail": "Jl. Mawar No. 12, Pasar Minggu. Pagar hitam, sebelah Masjid.",
            "scheduled_date": date.today(),
            "time_slot": PickupRequest.TimeSlot.S0810,
            "status": status,
            "verified_at": verified_at,
        }
        fields.update(overrides)
        pickup = PickupRequest.objects.create(**fields)
        item = PickupItem.objects.create(
            pickup_request=pickup,
            waste_type=self.waste_type,
            estimated_weight=Decimal("2.00"),
            actual_weight=Decimal("1.75") if status == Status.COMPLETED else None,
            unit_rate_snapshot=self.waste_type.rate_per_kg,
        )
        return pickup, item


class PickupIntegrationTests(PickupTestCase):
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
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
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
        self.assertEqual(data["status"], Status.ASSIGNED)
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
        pickup, _ = self.make_pickup(status=Status.COMPLETED)
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
        pickup, item = self.make_pickup(status=Status.COMPLETED)
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
        pickup, _ = self.make_pickup(status=Status.COMPLETED)
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

    def test_collector_completion_verifies_pickup_and_processes_incentive(self):
        pickup, item = self.make_pickup(status=Status.WEIGHING)
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
        self.assertEqual(
            response.json()["message"],
            "Pickup selesai diverifikasi dan insentif berhasil diproses.",
        )
        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(pickup.status, Status.COMPLETED)
        self.assertEqual(item.actual_weight, Decimal("1.75"))
        self.assertIsNotNone(pickup.verified_at)
        self.assertEqual(pickup.verified_by, self.collector)
        wallet_transaction = WalletTransaction.objects.get(reference=f"pickup:{pickup.pk}")
        self.assertEqual(wallet_transaction.amount, Decimal("14000.00"))


# --------------- Model ---------------


class PickupModelTests(PickupTestCase):
    def setUp(self):
        super().setUp()
        self.cardboard = WasteType.objects.create(
            name="Kardus Uji", rate_per_kg=Decimal("2000.00")
        )

    def add_cardboard(self, pickup, *, estimated="3.00", actual="2.50", rate="2000.00"):
        return PickupItem.objects.create(
            pickup_request=pickup,
            waste_type=self.cardboard,
            estimated_weight=Decimal(estimated),
            actual_weight=Decimal(actual) if actual is not None else None,
            unit_rate_snapshot=Decimal(rate) if rate is not None else None,
        )

    # --- representasi teks ---

    def test_str_representations(self):
        pickup, item = self.make_pickup()
        self.assertEqual(
            str(pickup), f"Pickup #{pickup.pk} - {pickup.get_status_display()}"
        )
        self.assertEqual(str(item), f"{self.waste_type} — {pickup}")

        initial = PickupStatusHistory.objects.create(
            pickup=pickup, previous_status="", new_status="PENDING"
        )
        change = PickupStatusHistory.objects.create(
            pickup=pickup, previous_status="PENDING", new_status="ASSIGNED"
        )
        self.assertEqual(str(initial), f"Pickup #{pickup.pk}: INITIAL -> PENDING")
        self.assertEqual(str(change), f"Pickup #{pickup.pk}: PENDING -> ASSIGNED")

    # --- transisi status ---

    def test_can_transition_to_follows_allowed_transitions(self):
        for current in Status:
            pickup = PickupRequest(status=current)
            for target in Status:
                with self.subTest(current=current.value, target=target.value):
                    expected = target in PickupRequest.ALLOWED_TRANSITIONS[current]
                    self.assertEqual(pickup.can_transition_to(target), expected)

    def test_can_transition_to_works_with_status_loaded_from_database(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        pickup = PickupRequest.objects.get(pk=pickup.pk)
        self.assertIsInstance(pickup.status, str)
        self.assertTrue(pickup.can_transition_to("ON_THE_WAY"))
        self.assertFalse(pickup.can_transition_to("COMPLETED"))

    def test_can_transition_to_is_false_for_unknown_status(self):
        pickup = PickupRequest(status="UNKNOWN")
        self.assertFalse(pickup.can_transition_to(Status.PENDING))

    def test_is_cancellable_only_for_pending_and_assigned(self):
        for status in Status:
            with self.subTest(status=status.value):
                pickup = PickupRequest(status=status)
                self.assertEqual(
                    pickup.is_cancellable,
                    status in (Status.PENDING, Status.ASSIGNED),
                )

    # --- total berat dan insentif ---

    def test_totals_without_items(self):
        pickup, _ = self.make_pickup()
        pickup.items.all().delete()

        self.assertEqual(pickup.estimated_weight, Decimal("0"))
        self.assertIsNone(pickup.actual_weight)
        self.assertEqual(pickup.estimated_reward, Decimal("0"))
        self.assertIsNone(pickup.actual_reward)

    def test_totals_with_priced_and_weighed_items(self):
        pickup, _ = self.make_pickup(status=Status.COMPLETED)  # 2.00 kg est, 1.75 kg act, Rp8.000
        self.add_cardboard(pickup)  # 3.00 kg est, 2.50 kg act, Rp2.000

        self.assertEqual(pickup.estimated_weight, Decimal("5.00"))
        self.assertEqual(pickup.actual_weight, Decimal("4.25"))
        self.assertEqual(pickup.estimated_reward, Decimal("22000"))
        self.assertEqual(pickup.actual_reward, Decimal("19000"))

    def test_actual_totals_are_none_until_every_item_is_weighed(self):
        pickup, _ = self.make_pickup(status=Status.WEIGHING)
        self.add_cardboard(pickup)

        self.assertEqual(pickup.estimated_weight, Decimal("5.00"))
        self.assertIsNone(pickup.actual_weight)
        self.assertIsNone(pickup.actual_reward)

    def test_rewards_are_none_when_a_rate_snapshot_is_missing(self):
        pickup, item = self.make_pickup(status=Status.COMPLETED)
        item.unit_rate_snapshot = None
        item.save(update_fields=["unit_rate_snapshot"])

        self.assertIsNone(pickup.estimated_reward)
        self.assertIsNone(pickup.actual_reward)

    def test_item_subtotals(self):
        item = PickupItem(
            estimated_weight=Decimal("2.00"),
            actual_weight=Decimal("1.50"),
            unit_rate_snapshot=Decimal("8000.00"),
        )
        self.assertEqual(item.estimated_subtotal, Decimal("16000"))
        self.assertEqual(item.actual_subtotal, Decimal("12000"))

        item.actual_weight = None
        self.assertEqual(item.estimated_subtotal, Decimal("16000"))
        self.assertIsNone(item.actual_subtotal)

        item.actual_weight = Decimal("1.50")
        item.unit_rate_snapshot = None
        self.assertIsNone(item.estimated_subtotal)
        self.assertIsNone(item.actual_subtotal)

    # --- constraint database ---

    def test_active_statuses_require_a_collector(self):
        active = (
            Status.ASSIGNED,
            Status.ON_THE_WAY,
            Status.ARRIVED,
            Status.WEIGHING,
            Status.COMPLETED,
        )
        for status in active:
            with self.subTest(status=status.value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_pickup(status=status, collector=None)

    def test_inactive_statuses_do_not_require_a_collector(self):
        for status in (Status.PENDING, Status.CANCELLED, Status.FAILED):
            with self.subTest(status=status.value):
                pickup, _ = self.make_pickup(status=status, collector=None)
                self.assertIsNone(pickup.collector)

    def test_coordinates_must_be_provided_together(self):
        for overrides in (
            {"latitude": Decimal("-6.2000000")},
            {"longitude": Decimal("106.8000000")},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_pickup(**overrides)

        with_both, _ = self.make_pickup(
            latitude=Decimal("-6.2000000"), longitude=Decimal("106.8000000")
        )
        without, _ = self.make_pickup()
        self.assertEqual(with_both.latitude, Decimal("-6.2000000"))
        self.assertIsNone(without.latitude)
        self.assertIsNone(without.longitude)

    def test_waste_type_is_unique_per_pickup(self):
        pickup, _ = self.make_pickup()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PickupItem.objects.create(
                pickup_request=pickup,
                waste_type=self.waste_type,
                estimated_weight=Decimal("1.00"),
            )

        # jenis lain pada pickup yang sama tetap boleh
        self.add_cardboard(pickup)
        self.assertEqual(pickup.items.count(), 2)

    # --- validator ---

    def test_field_validators(self):
        pickup, item = self.make_pickup()

        pickup.pickup_address = "abc"
        with self.assertRaises(ValidationError) as ctx:
            pickup.clean_fields()
        self.assertIn("pickup_address", ctx.exception.message_dict)

        item.estimated_weight = Decimal("0.00")
        with self.assertRaises(ValidationError) as ctx:
            item.clean_fields()
        self.assertIn("estimated_weight", ctx.exception.message_dict)

        item.estimated_weight = Decimal("1.00")
        item.actual_weight = Decimal("0.00")
        with self.assertRaises(ValidationError) as ctx:
            item.clean_fields()
        self.assertIn("actual_weight", ctx.exception.message_dict)

    # --- urutan dan relasi ---

    def test_default_ordering_is_newest_first(self):
        older, _ = self.make_pickup()
        newer, _ = self.make_pickup()
        PickupRequest.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        self.assertEqual(
            list(PickupRequest.objects.values_list("pk", flat=True)),
            [newer.pk, older.pk],
        )

    def test_history_is_ordered_oldest_first(self):
        pickup, _ = self.make_pickup()
        second = PickupStatusHistory.objects.create(
            pickup=pickup, previous_status="PENDING", new_status="ASSIGNED"
        )
        first = PickupStatusHistory.objects.create(pickup=pickup, new_status="PENDING")
        PickupStatusHistory.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        PickupStatusHistory.objects.filter(pk=second.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

        self.assertEqual(
            list(pickup.status_history.values_list("pk", flat=True)),
            [first.pk, second.pk],
        )

    def test_deleting_pickup_cascades_to_items_and_history(self):
        pickup, _ = self.make_pickup()
        PickupStatusHistory.objects.create(pickup=pickup, new_status="PENDING")

        pickup.delete()

        self.assertEqual(PickupItem.objects.count(), 0)
        self.assertEqual(PickupStatusHistory.objects.count(), 0)

    def test_giver_and_waste_type_are_protected_from_deletion(self):
        self.make_pickup()
        with self.assertRaises(ProtectedError):
            self.waste_type.delete()
        with self.assertRaises(ProtectedError):
            self.giver.delete()


# ------------- Services -------------


class PickupServiceTests(PickupTestCase):
    def new_pickup_instance(self, **overrides):
        return PickupRequest(
            pickup_address="Jl. Melati No. 5, Pasar Minggu",
            scheduled_date=date.today(),
            time_slot=PickupRequest.TimeSlot.S1012,
            **overrides,
        )

    def test_service_error_defaults(self):
        error = services.PickupServiceError("gagal")
        self.assertEqual(error.message, "gagal")
        self.assertEqual(error.status_code, 400)
        self.assertEqual(str(error), "gagal")
        self.assertEqual(services.PickupServiceError("x", status_code=409).status_code, 409)

    # --- create_pickup ---

    def test_create_pickup_sets_giver_pending_status_and_initial_history(self):
        pickup = services.create_pickup(
            self.new_pickup_instance(status=Status.ASSIGNED), self.giver
        )

        pickup.refresh_from_db()
        self.assertEqual(pickup.giver, self.giver)
        self.assertEqual(pickup.status, Status.PENDING)
        entry = pickup.status_history.get()
        self.assertEqual(entry.previous_status, "")
        self.assertEqual(entry.new_status, Status.PENDING)
        self.assertEqual(entry.changed_by, self.giver)

    # --- penugasan ---

    def test_collector_can_accept_pending_pickup(self):
        pickup, _ = self.make_pickup()

        result = services.change_status(
            pickup.pk, Status.ASSIGNED, self.collector, collector=self.collector
        )

        self.assertEqual(result.status, Status.ASSIGNED)
        pickup.refresh_from_db()
        self.assertEqual(pickup.collector, self.collector)
        self.assertIsNotNone(pickup.assigned_at)
        entry = pickup.status_history.get()
        self.assertEqual(entry.previous_status, "PENDING")
        self.assertEqual(entry.new_status, "ASSIGNED")
        self.assertEqual(entry.changed_by, self.collector)

    def test_assignment_requires_a_collector_argument(self):
        pickup, _ = self.make_pickup()

        with self.assertRaises(services.PickupServiceError) as ctx:
            services.change_status(pickup.pk, Status.ASSIGNED, self.collector)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.message, "Kurir wajib ditentukan.")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.PENDING)
        self.assertFalse(pickup.status_history.exists())

    def test_assigned_collector_can_release_the_task(self):
        pickup, _ = self.make_pickup(
            status=Status.ASSIGNED, assigned_at=timezone.now()
        )

        services.change_status(pickup.pk, Status.PENDING, self.collector)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.PENDING)
        self.assertIsNone(pickup.collector)
        self.assertIsNone(pickup.assigned_at)

    # --- pembatalan ---

    def test_giver_can_cancel_pending_pickup_with_reason(self):
        pickup, _ = self.make_pickup()

        services.change_status(
            pickup.pk, Status.CANCELLED, self.giver, reason="Salah alamat"
        )

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.CANCELLED)
        self.assertEqual(pickup.status_reason, "Salah alamat")
        self.assertIsNotNone(pickup.cancelled_at)
        self.assertEqual(pickup.status_history.get().note, "Salah alamat")

    def test_giver_can_cancel_assigned_pickup(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)

        services.change_status(pickup.pk, Status.CANCELLED, self.giver)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.CANCELLED)

    # --- progres kurir ---

    def test_assigned_collector_can_progress_through_weighing(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)

        for target in (Status.ON_THE_WAY, Status.ARRIVED, Status.WEIGHING):
            with self.subTest(target=target.value):
                result = services.change_status(pickup.pk, target, self.collector)
                self.assertEqual(result.status, target)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.WEIGHING)
        self.assertEqual(
            list(pickup.status_history.values_list("new_status", flat=True)),
            ["ON_THE_WAY", "ARRIVED", "WEIGHING"],
        )

    def test_reason_is_only_stored_on_pickup_for_cancelled_and_failed(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)

        services.change_status(
            pickup.pk, Status.ON_THE_WAY, self.collector, reason="catatan"
        )

        pickup.refresh_from_db()
        self.assertEqual(pickup.status_reason, "")
        self.assertEqual(pickup.status_history.get().note, "catatan")

    def test_failed_requires_reason(self):
        pickup, _ = self.make_pickup(status=Status.ON_THE_WAY)

        with self.assertRaises(services.PickupServiceError) as ctx:
            services.change_status(pickup.pk, Status.FAILED, self.collector)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.message, "Alasan kegagalan wajib diisi.")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ON_THE_WAY)

        services.change_status(
            pickup.pk, Status.FAILED, self.collector, reason="Pemilik tidak ada"
        )
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.FAILED)
        self.assertEqual(pickup.status_reason, "Pemilik tidak ada")
        self.assertEqual(pickup.status_history.get().note, "Pemilik tidak ada")

    # --- aturan transisi ---

    def test_invalid_transition_returns_conflict(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)

        with self.assertRaises(services.PickupServiceError) as ctx:
            services.change_status(pickup.pk, Status.ARRIVED, self.collector)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn(pickup.get_status_display(), ctx.exception.message)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ASSIGNED)
        self.assertFalse(pickup.status_history.exists())

    def test_finished_pickup_cannot_change_again(self):
        pickup, _ = self.make_pickup(status=Status.COMPLETED)

        with self.assertRaises(services.PickupServiceError) as ctx:
            services.change_status(pickup.pk, Status.CANCELLED, self.giver)

        self.assertEqual(ctx.exception.status_code, 409)

    def test_unknown_pickup_raises_404(self):
        with self.assertRaises(Http404):
            services.change_status(uuid.uuid4(), Status.CANCELLED, self.giver)

    # --- otorisasi ---

    def test_unauthorized_actors_are_denied_and_nothing_changes(self):
        pending, _ = self.make_pickup()
        assigned, _ = self.make_pickup(status=Status.ASSIGNED)
        denied = [
            ("non-collector accepting", pending, Status.ASSIGNED, self.giver),
            ("stranger cancelling", pending, Status.CANCELLED, self.other_giver),
            ("collector cancelling", assigned, Status.CANCELLED, self.collector),
            ("giver progressing", assigned, Status.ON_THE_WAY, self.giver),
            ("other collector progressing", assigned, Status.ON_THE_WAY, self.other_collector),
        ]
        for label, pickup, target, actor in denied:
            with self.subTest(label):
                before = pickup.status
                with self.assertRaises(PermissionDenied):
                    services.change_status(pickup.pk, target, actor, collector=actor)
                pickup.refresh_from_db()
                self.assertEqual(pickup.status, before)
                self.assertFalse(pickup.status_history.exists())

    def test_admin_can_bypass_role_checks(self):
        pending, _ = self.make_pickup()
        assigned, _ = self.make_pickup(status=Status.ASSIGNED)

        with mock.patch("pickup.services.is_admin", return_value=True):
            cancelled = services.change_status(
                pending.pk, Status.CANCELLED, self.other_giver, reason="Oleh admin"
            )
            moved = services.change_status(
                assigned.pk, Status.ON_THE_WAY, self.other_giver
            )

        self.assertEqual(cancelled.status, Status.CANCELLED)
        self.assertEqual(moved.status, Status.ON_THE_WAY)


# ---------- View dan endpoint AJAX ----------


class PickupViewTests(PickupTestCase):
    def url(self, name, pickup=None):
        kwargs = {"pickup_id": pickup.pk} if pickup is not None else None
        return reverse(f"pickup:{name}", kwargs=kwargs)

    def weighing_payload(self, item, weight):
        return {
            "weigh-TOTAL_FORMS": "1",
            "weigh-INITIAL_FORMS": "1",
            "weigh-MIN_NUM_FORMS": "0",
            "weigh-MAX_NUM_FORMS": "1000",
            "weigh-0-id": str(item.pk),
            "weigh-0-actual_weight": weight,
        }

    # --- halaman detail ---

    def test_detail_page_requires_login(self):
        pickup, _ = self.make_pickup()
        response = self.client.get(self.url("show_pickup_detail", pickup))
        self.assertEqual(response.status_code, 302)

    def test_detail_page_access_rules(self):
        pending, _ = self.make_pickup()
        assigned, _ = self.make_pickup(status=Status.ASSIGNED)
        cases = [
            (self.giver, pending, 200),
            (self.other_giver, pending, 404),
            (self.collector, pending, 200),  # pickup menunggu terbuka bagi semua collector
            (self.other_collector, pending, 200),
            (self.giver, assigned, 200),
            (self.other_giver, assigned, 404),
            (self.collector, assigned, 200),
            (self.other_collector, assigned, 404),
        ]
        for user, pickup, expected in cases:
            with self.subTest(user=user.username, status=pickup.status):
                self.client.force_login(user)
                response = self.client.get(self.url("show_pickup_detail", pickup))
                self.assertEqual(response.status_code, expected)

    def test_detail_page_is_open_to_admin(self):
        assigned, _ = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.other_giver)
        with mock.patch("pickup.views.is_admin", return_value=True):
            response = self.client.get(self.url("show_pickup_detail", assigned))
        self.assertEqual(response.status_code, 200)

    # --- JSON: daftar giver ---

    def test_giver_pickup_json_requires_giver_role(self):
        url = self.url("get_pickup_json")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_giver_pickup_json_lists_only_own_pickups_and_filters(self):
        mine, _ = self.make_pickup()
        cancelled, _ = self.make_pickup(status=Status.CANCELLED)
        self.make_pickup(giver=self.other_giver)
        self.client.force_login(self.giver)
        url = self.url("get_pickup_json")

        everything = self.client.get(url).json()
        self.assertEqual(
            {row["pk"] for row in everything}, {str(mine.pk), str(cancelled.pk)}
        )

        by_status = self.client.get(url, {"status": "CANCELLED"}).json()
        self.assertEqual([row["pk"] for row in by_status], [str(cancelled.pk)])
        self.assertEqual(self.client.get(url, {"status": "BOGUS"}).json(), [])

        by_id = self.client.get(url, {"q": str(mine.pk)}).json()
        self.assertEqual([row["pk"] for row in by_id], [str(mine.pk)])
        self.assertEqual(self.client.get(url, {"q": "bukan-uuid"}).json(), [])

    # --- JSON: daftar collector ---

    def test_collector_pickup_json_requires_collector_role(self):
        url = self.url("get_collector_pickup_json")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.giver)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_collector_pickup_json_rejects_invalid_scope(self):
        self.client.force_login(self.collector)
        response = self.client.get(
            self.url("get_collector_pickup_json"), {"scope": "all"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Scope tidak valid.")

    def test_collector_pickup_json_filters_by_status_and_id(self):
        assigned, _ = self.make_pickup(status=Status.ASSIGNED)
        failed, _ = self.make_pickup(status=Status.FAILED)
        self.make_pickup(status=Status.ASSIGNED, collector=self.other_collector)
        self.client.force_login(self.collector)
        url = self.url("get_collector_pickup_json")

        everything = self.client.get(url).json()
        self.assertEqual(
            {row["pk"] for row in everything}, {str(assigned.pk), str(failed.pk)}
        )
        by_status = self.client.get(url, {"status": "FAILED"}).json()
        self.assertEqual([row["pk"] for row in by_status], [str(failed.pk)])
        self.assertEqual(self.client.get(url, {"status": "BOGUS"}).json(), [])
        by_id = self.client.get(url, {"q": str(assigned.pk)}).json()
        self.assertEqual([row["pk"] for row in by_id], [str(assigned.pk)])
        self.assertEqual(self.client.get(url, {"q": "bukan-uuid"}).json(), [])

    # --- JSON: detail ---

    def test_pickup_detail_json_requires_login_and_access(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        url = self.url("get_pickup_detail_json", pickup)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.other_giver)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_pickup_detail_json_hides_contact_from_unrelated_collectors(self):
        pickup, _ = self.make_pickup(contact_phone="081234567890")
        PickupStatusHistory.objects.create(
            pickup=pickup,
            new_status="PENDING",
            changed_by=self.giver,
            note="Dibuat",
        )
        url = self.url("get_pickup_detail_json", pickup)

        self.client.force_login(self.giver)
        owner = self.client.get(url).json()
        self.assertEqual(owner["pk"], str(pickup.pk))
        self.assertEqual(owner["fields"]["contact_phone"], "081234567890")
        self.assertTrue(owner["fields"]["is_cancellable"])
        self.assertEqual(owner["history"][0]["note"], "Dibuat")
        self.assertEqual(owner["history"][0]["new_status_display"], "Menunggu Penugasan")

        self.client.force_login(self.other_collector)
        visitor = self.client.get(url).json()
        self.assertIsNone(visitor["fields"]["contact_phone"])
        self.assertFalse(visitor["fields"]["is_cancellable"])

    # --- metode dan autentikasi endpoint action ---

    def test_action_endpoints_only_accept_post(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.giver)
        for name in (
            "cancel_pickup_ajax",
            "accept_pickup_ajax",
            "update_pickup_status_ajax",
            "complete_weighing_ajax",
        ):
            with self.subTest(name):
                self.assertEqual(
                    self.client.get(self.url(name, pickup)).status_code, 405
                )
        self.assertEqual(self.client.get(self.url("create_pickup_ajax")).status_code, 405)

    def test_action_endpoints_require_authentication(self):
        pickup, _ = self.make_pickup()
        for name in (
            "cancel_pickup_ajax",
            "accept_pickup_ajax",
            "update_pickup_status_ajax",
            "complete_weighing_ajax",
        ):
            with self.subTest(name):
                response = self.client.post(self.url(name, pickup))
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.post(self.url("create_pickup_ajax")).status_code, 401)

    # --- create ---

    def test_create_pickup_ajax_rejects_invalid_data(self):
        url = self.url("create_pickup_ajax")

        self.client.force_login(self.giver)
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())
        self.assertEqual(PickupRequest.objects.count(), 0)

    # --- batalkan ---

    def test_giver_can_cancel_pending_pickup(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.giver)

        response = self.client.post(
            self.url("cancel_pickup_ajax", pickup), {"reason": "Salah alamat"}
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pk"], str(pickup.pk))
        self.assertEqual(body["status"], "CANCELLED")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.CANCELLED)
        self.assertEqual(pickup.status_reason, "Salah alamat")
        self.assertIsNotNone(pickup.cancelled_at)

    def test_cancel_is_rejected_for_other_users_and_finished_pickups(self):
        pending, _ = self.make_pickup()
        completed, _ = self.make_pickup(status=Status.COMPLETED)

        self.client.force_login(self.other_giver)
        response = self.client.post(self.url("cancel_pickup_ajax", pending))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Anda tidak memiliki akses.")

        self.client.force_login(self.giver)
        response = self.client.post(self.url("cancel_pickup_ajax", completed))
        self.assertEqual(response.status_code, 409)
        self.assertIn("error", response.json())

        pending.refresh_from_db()
        self.assertEqual(pending.status, Status.PENDING)

    # --- terima tugas ---

    def test_collector_can_accept_pending_pickup(self):
        pickup, _ = self.make_pickup()
        self.client.force_login(self.collector)

        response = self.client.post(self.url("accept_pickup_ajax", pickup))

        self.assertEqual(response.json()["status"], "ASSIGNED")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ASSIGNED)
        self.assertEqual(pickup.collector, self.collector)

    def test_accept_is_rejected_for_non_collectors_and_taken_pickups(self):
        pending, _ = self.make_pickup()
        taken, _ = self.make_pickup(status=Status.ASSIGNED)

        self.client.force_login(self.giver)
        self.assertEqual(
            self.client.post(self.url("accept_pickup_ajax", pending)).status_code, 403
        )

        self.client.force_login(self.other_collector)
        response = self.client.post(self.url("accept_pickup_ajax", taken))
        taken.refresh_from_db()
        self.assertEqual(taken.collector, self.collector)

    # --- ubah status ---

    def test_update_status_rejects_invalid_target_status(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)
        url = self.url("update_pickup_status_ajax", pickup)

        for value in ("", "BOGUS", "ASSIGNED", "CANCELLED"):
            with self.subTest(status=value):
                response = self.client.post(url, {"status": value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "Status tujuan tidak valid.")

    def test_assigned_collector_can_update_status(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)
        url = self.url("update_pickup_status_ajax", pickup)

        response = self.client.post(url, {"status": "ON_THE_WAY"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ON_THE_WAY")
        self.assertEqual(body["status_display"], "Kurir Dalam Perjalanan")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ON_THE_WAY)

    def test_update_status_rejects_invalid_transition(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)

        response = self.client.post(
            self.url("update_pickup_status_ajax", pickup), {"status": "ARRIVED"}
        )

        self.assertEqual(response.status_code, 409)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ASSIGNED)

    def test_update_status_to_failed_requires_note(self):
        pickup, _ = self.make_pickup(status=Status.ON_THE_WAY)
        self.client.force_login(self.collector)
        url = self.url("update_pickup_status_ajax", pickup)

        missing = self.client.post(url, {"status": "FAILED", "note": "   "})
        self.assertEqual(missing.status_code, 400)

        response = self.client.post(
            url, {"status": "FAILED", "note": "Alamat tidak ditemukan"}
        )
        self.assertEqual(response.status_code, 200)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.FAILED)
        self.assertEqual(pickup.status_reason, "Alamat tidak ditemukan")

    def test_update_status_is_forbidden_for_unrelated_users(self):
        pickup, _ = self.make_pickup(status=Status.ASSIGNED)
        url = self.url("update_pickup_status_ajax", pickup)

        for user in (self.giver, self.other_collector):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.post(url, {"status": "ON_THE_WAY"})
                self.assertEqual(response.status_code, 403)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.ASSIGNED)

    # --- penimbangan ---

    def test_complete_weighing_is_forbidden_for_unrelated_users(self):
        pickup, item = self.make_pickup(status=Status.WEIGHING)
        url = self.url("complete_weighing_ajax", pickup)

        for user in (self.giver, self.other_collector):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.post(url, self.weighing_payload(item, "1.75"))
                self.assertEqual(response.status_code, 403)

        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(pickup.status, Status.WEIGHING)
        self.assertIsNone(item.actual_weight)

    def test_complete_weighing_requires_weighing_stage(self):
        pickup, item = self.make_pickup(status=Status.ARRIVED)
        self.client.force_login(self.collector)

        response = self.client.post(
            self.url("complete_weighing_ajax", pickup),
            self.weighing_payload(item, "1.75"),
        )

        self.assertEqual(response.status_code, 400)
        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(pickup.status, Status.ARRIVED)
        self.assertIsNone(item.actual_weight)

    def test_complete_weighing_rejects_invalid_weights(self):
        pickup, item = self.make_pickup(status=Status.WEIGHING)
        self.client.force_login(self.collector)
        url = self.url("complete_weighing_ajax", pickup)

        for weight in ("0", "abc"):
            with self.subTest(weight=weight):
                response = self.client.post(url, self.weighing_payload(item, weight))
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())

        pickup.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(pickup.status, Status.WEIGHING)
        self.assertIsNone(item.actual_weight)