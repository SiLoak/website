from decimal import Decimal

from django.urls import reverse

from pickup.models import PickupStatusHistory

from .helpers import PickupTestCase, Status


class PickupEditTests(PickupTestCase):
    def edit_url(self, pickup):
        return reverse("pickup:edit", args=[pickup.pk])

    def edit_payload(self, pickup, **overrides):
        item = pickup.items.get()
        data = self.pickup_payload(**{
            "items-INITIAL_FORMS": "1",
            "items-0-id": str(item.pk),
            "items-0-pickup_request": str(pickup.pk),
        })
        data.update(overrides)
        return data

    def test_owner_sees_form_prefilled_with_the_pickup(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.get(self.edit_url(pickup))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["editing_pickup"])
        self.assertContains(response, "Jl. Mawar No. 12, Pasar Minggu")
        self.assertEqual(response.context["pickup_form"]["pickup_date_option"].value(), "tomorrow")

    def test_owner_can_update_address_schedule_and_items(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.post(self.edit_url(pickup), self.edit_payload(
            pickup,
            **{"items-0-waste_type": str(self.other_type.pk), "items-0-estimated_weight": "7.00",
               "time_slot": "14:00-16:00", "courier_note": "Titip satpam"},
        ))

        self.assertRedirects(response, reverse("pickup:show_pickup_detail", args=[pickup.pk]))
        pickup.refresh_from_db()
        item = pickup.items.get()
        self.assertEqual(pickup.pickup_address, "Jl. Melati No. 3, Tebet, Jakarta Selatan")
        self.assertEqual(pickup.time_slot, "14:00-16:00")
        self.assertEqual(pickup.courier_note, "Titip satpam")
        self.assertEqual(item.waste_type, self.other_type)
        self.assertEqual(item.estimated_weight, Decimal("7.00"))
        self.assertEqual(item.unit_rate_snapshot, self.other_type.rate_per_kg)
        self.assertTrue(PickupStatusHistory.objects.filter(pickup=pickup, note="Permintaan penjemputan diperbarui.").exists())

    def test_invalid_edit_shows_errors_and_keeps_data(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        response = self.client.post(self.edit_url(pickup), self.edit_payload(pickup, contact_phone="123"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("contact_phone", response.context["pickup_form"].errors)
        pickup.refresh_from_db()
        self.assertEqual(pickup.contact_phone, "081234567890")

    def test_other_users_cannot_open_or_change_the_pickup(self):
        pickup = self.make_pickup()
        self.client.force_login(self.other_giver)

        self.assertEqual(self.client.get(self.edit_url(pickup)).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url(pickup), self.edit_payload(pickup)).status_code, 404)

    def test_pickup_that_left_pending_is_locked(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.giver)
        response = self.client.get(self.edit_url(pickup))

        self.assertRedirects(response, reverse("pickup:show_pickup_detail", args=[pickup.pk]))

    def test_detail_page_links_to_edit_only_while_pending(self):
        pending = self.make_pickup()
        assigned = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.giver)

        self.assertContains(self.client.get(reverse("pickup:show_pickup_detail", args=[pending.pk])), self.edit_url(pending))
        self.assertNotContains(self.client.get(reverse("pickup:show_pickup_detail", args=[assigned.pk])), self.edit_url(assigned))


class PickupListPageTests(PickupTestCase):
    def test_pickup_index_redirects_givers_to_filtered_history(self):
        self.client.force_login(self.giver)
        response = self.client.get(reverse("pickup:show_pickup_list"))

        self.assertRedirects(response, reverse("waste:submissions") + "?type=pickup", fetch_redirect_response=False)

    def test_collectors_are_sent_to_their_dashboard(self):
        self.client.force_login(self.collector)
        response = self.client.get(reverse("pickup:show_pickup_list"))

        self.assertEqual(response.status_code, 403)
