from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pickup.models import PickupRequest
from .models import CollectionPoint, Submission, SubmissionItem, WasteType


class WasteSubmissionFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="giver", email="giver@example.com", password="secret"
        )
        self.other_user = User.objects.create_user(
            username="other", email="other@example.com", password="secret"
        )
        self.waste_type = WasteType.objects.create(
            name="Kardus Uji", rate_per_kg=Decimal("5000.00")
        )
        self.point = CollectionPoint.objects.create(
            name="Depo Pasar Minggu Uji",
            address="Jl. Raya Pasar Minggu No. 14",
            operating_hours="08.00 - 16.00 WIB",
        )

    def submission_payload(self, estimated_weight="2.50"):
        return {
            "collection_point": str(self.point.pk),
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "6",
            "items-0-waste_type": str(self.waste_type.pk),
            "items-0-estimated_weight": estimated_weight,
        }

    def make_submission(self, *, status=Submission.Status.PENDING):
        submission = Submission.objects.create(
            user=self.user, collection_point=self.point, status=status
        )
        item = SubmissionItem.objects.create(
            submission=submission,
            waste_type=self.waste_type,
            estimated_weight=Decimal("2.50"),
            unit_rate_snapshot=self.waste_type.rate_per_kg,
        )
        return submission, item

    def test_migration_seeds_template_catalog_and_collection_points(self):
        self.assertTrue(
            WasteType.objects.filter(
                name="Botol plastik (PET bening)", rate_per_kg=Decimal("8000.00")
            ).exists()
        )
        self.assertTrue(
            CollectionPoint.objects.filter(name="Bank Sampah Tebet Hijau").exists()
        )

    def test_anonymous_submission_redirects_to_login_with_return_path(self):
        response = self.client.get(reverse("waste:new"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/auth/?next=/waste/new/")

        login_page = self.client.get(response.url)
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(
            login_page,
            "/auth/google/login/?next=/waste/new/",
        )

    def test_signed_in_user_can_open_form_and_create_submission(self):
        self.client.force_login(self.user)

        page = self.client.get(reverse("waste:new"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Kardus Uji — Rp 5.000/kg")
        self.assertContains(page, "Depo Pasar Minggu Uji — Jl. Raya Pasar Minggu No. 14")
        selected_point_id = page.context["form"]["collection_point"].value()
        selected_point = CollectionPoint.objects.get(pk=selected_point_id)
        self.assertIn("Pasar Minggu", selected_point.name)
        self.assertEqual(
            page.context["form"]["incentive_allocation"].value(),
            Submission.IncentiveAllocation.WALLET,
        )
        self.assertRedirects(
            self.client.get(reverse("waste:dropoff")),
            reverse("waste:new"),
        )

        response = self.client.post(
            reverse("waste:new"), self.submission_payload()
        )

        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(user=self.user)
        self.assertRedirects(
            response,
            reverse("waste:detail", kwargs={"submission_id": submission.pk}),
        )
        item = submission.items.get()
        self.assertEqual(submission.status, Submission.Status.PENDING)
        self.assertEqual(item.estimated_weight, Decimal("2.50"))
        self.assertEqual(item.unit_rate_snapshot, Decimal("5000.00"))

    def test_donation_choice_is_saved_and_pickup_is_not_submitted_by_waste_flow(self):
        self.client.force_login(self.user)
        payload = self.submission_payload()
        payload["incentive_allocation"] = Submission.IncentiveAllocation.DONATION

        response = self.client.post(reverse("waste:new"), payload)

        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(user=self.user)
        self.assertEqual(
            submission.incentive_allocation,
            Submission.IncentiveAllocation.DONATION,
        )

        pickup_payload = self.submission_payload()
        pickup_payload["delivery_method"] = "minta_dijemput"
        rejected_pickup = self.client.post(reverse("waste:new"), pickup_payload)
        self.assertEqual(rejected_pickup.status_code, 200)
        self.assertEqual(Submission.objects.filter(user=self.user).count(), 1)

    def test_pickup_choice_creates_pickup_from_shared_submission_form(self):
        self.client.force_login(self.user)
        payload = self.submission_payload()
        payload.update(
            {
                "delivery_method": "minta_dijemput",
                "address_detail": "Jl. Mawar No. 12, gerbang hijau",
                "contact_phone": "081234567890",
                "latitude": "",
                "longitude": "",
                "time_slot": "08:00-10:00",
                "pickup_date_option": "tomorrow",
                "custom_date": "",
            }
        )

        response = self.client.post(reverse("waste:new"), payload)

        pickup = PickupRequest.objects.get(giver=self.user)
        self.assertRedirects(
            response,
            reverse("pickup:show_pickup_detail", kwargs={"pickup_id": pickup.pk}),
        )
        self.assertEqual(pickup.status, PickupRequest.Status.PENDING)
        self.assertEqual(pickup.pickup_address, payload["address_detail"])
        self.assertEqual(pickup.items.get().unit_rate_snapshot, self.waste_type.rate_per_kg)
        self.assertFalse(Submission.objects.filter(user=self.user).exists())

    def test_form_rejects_nonpositive_weights_duplicate_types_and_more_than_six_items(self):
        self.client.force_login(self.user)

        invalid_weight = self.client.post(
            reverse("waste:new"), self.submission_payload("0")
        )
        self.assertEqual(invalid_weight.status_code, 200)
        self.assertFalse(Submission.objects.exists())

        duplicate_payload = self.submission_payload()
        duplicate_payload.update(
            {
                "items-TOTAL_FORMS": "2",
                "items-1-waste_type": str(self.waste_type.pk),
                "items-1-estimated_weight": "1.00",
            }
        )
        duplicate = self.client.post(reverse("waste:new"), duplicate_payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(Submission.objects.exists())

        distinct_types = [self.waste_type]
        distinct_types.extend(
            WasteType.objects.create(name=f"Material {index}")
            for index in range(6)
        )
        too_many_payload = {
            "collection_point": str(self.point.pk),
            "items-TOTAL_FORMS": "7",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "6",
        }
        for index, waste_type in enumerate(distinct_types):
            too_many_payload[f"items-{index}-waste_type"] = str(waste_type.pk)
            too_many_payload[f"items-{index}-estimated_weight"] = "1.00"
        too_many = self.client.post(reverse("waste:new"), too_many_payload)
        self.assertEqual(too_many.status_code, 200)
        self.assertFalse(Submission.objects.exists())

    def test_form_rejects_inactive_waste_types_and_collection_points(self):
        self.client.force_login(self.user)

        self.waste_type.is_active = False
        self.waste_type.save(update_fields=["is_active"])
        inactive_type = self.client.post(
            reverse("waste:new"), self.submission_payload()
        )
        self.assertEqual(inactive_type.status_code, 200)
        self.assertFalse(Submission.objects.exists())

        self.waste_type.is_active = True
        self.waste_type.save(update_fields=["is_active"])
        self.point.is_active = False
        self.point.save(update_fields=["is_active"])
        inactive_point = self.client.post(
            reverse("waste:new"), self.submission_payload()
        )
        self.assertEqual(inactive_point.status_code, 200)
        self.assertFalse(Submission.objects.exists())

    def test_owner_can_edit_pending_submission_and_cannot_access_another_users_detail(self):
        submission, item = self.make_submission()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("waste:edit", kwargs={"submission_id": submission.pk}),
            {
                "collection_point": str(self.point.pk),
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "6",
                "items-0-id": str(item.pk),
                "items-0-waste_type": str(self.waste_type.pk),
                "items-0-estimated_weight": "3.25",
                "items-1-waste_type": "",
                "items-1-estimated_weight": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.estimated_weight, Decimal("3.25"))

        other_client = self.client_class()
        other_client.force_login(self.other_user)
        denied = other_client.get(
            reverse("waste:detail", kwargs={"submission_id": submission.pk})
        )
        self.assertEqual(denied.status_code, 404)

    def test_pending_submission_can_be_canceled_but_verified_submission_is_locked(self):
        pending, _ = self.make_submission()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("waste:cancel", kwargs={"submission_id": pending.pk})
        )
        self.assertEqual(response.status_code, 302)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Submission.Status.CANCELED)
        self.assertIsNotNone(pending.canceled_at)

        verified, _ = self.make_submission(status=Submission.Status.VERIFIED)
        response = self.client.post(
            reverse("waste:cancel", kwargs={"submission_id": verified.pk})
        )
        self.assertEqual(response.status_code, 302)
        verified.refresh_from_db()
        self.assertEqual(verified.status, Submission.Status.VERIFIED)

        response = self.client.post(
            reverse("waste:edit", kwargs={"submission_id": verified.pk}),
            self.submission_payload("9.00"),
        )
        self.assertEqual(response.status_code, 302)
        verified.refresh_from_db()
        self.assertEqual(verified.items.get().estimated_weight, Decimal("2.50"))

    def test_history_and_detail_show_only_the_signed_in_users_submissions(self):
        submission, _ = self.make_submission()
        self.client.force_login(self.user)

        history = self.client.get(reverse("history"))
        self.assertRedirects(history, reverse("waste:submissions"))

        listing = self.client.get(reverse("waste:submissions"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, f"#{submission.pk}")
        self.assertContains(listing, "Depo Pasar Minggu")
        self.assertContains(listing, submission.get_status_display())

        detail = self.client.get(
            reverse("waste:detail", kwargs={"submission_id": submission.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Perkiraan: 2,50 kg")

    def test_admin_records_actual_weight_then_verifies_only_complete_submissions(self):
        User = get_user_model()
        staff = User.objects.create_superuser(
            username="staff", email="staff@example.com", password="secret"
        )
        weighed, item = self.make_submission()
        incomplete, _ = self.make_submission()
        self.client.force_login(staff)

        change_url = reverse("admin:waste_submission_change", args=[weighed.pk])
        change_page = self.client.get(change_url)
        self.assertEqual(change_page.status_code, 200)
        self.assertContains(change_page, 'name="items-0-actual_weight"')

        response = self.client.post(
            change_url,
            {
                "_save": "Save",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": str(item.pk),
                "items-0-submission": str(weighed.pk),
                "items-0-waste_type": str(self.waste_type.pk),
                "items-0-actual_weight": "2.25",
            },
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.actual_weight, Decimal("2.25"))

        response = self.client.post(
            reverse("admin:waste_submission_changelist"),
            {
                "action": "verify_submissions",
                "index": "0",
                "_selected_action": [str(weighed.pk), str(incomplete.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        weighed.refresh_from_db()
        incomplete.refresh_from_db()
        self.assertEqual(weighed.status, Submission.Status.VERIFIED)
        self.assertEqual(weighed.verified_by, staff)
        self.assertEqual(incomplete.status, Submission.Status.PENDING)

        self.client.force_login(self.user)
        detail = self.client.get(
            reverse("waste:detail", kwargs={"submission_id": weighed.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Berat aktual")
        self.assertContains(detail, "2,25 kg")
