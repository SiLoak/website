from django.contrib.admin.sites import site
from django.urls import reverse

from pickup.models import PickupRequest

from .helpers import PickupTestCase, Status

CHANGELIST = reverse("admin:pickup_pickuprequest_changelist")


class PickupAdminTests(PickupTestCase):
    def setUp(self):
        super().setUp()
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)

    def run_action(self, action, pickups):
        return self.client.post(CHANGELIST, {
            "action": action,
            "_selected_action": [str(pickup.pk) for pickup in pickups],
        }, follow=True)

    def test_pickup_request_is_registered(self):
        self.assertIn(PickupRequest, site._registry)

    def test_changelist_filters_by_status_and_searches_address(self):
        pending = self.make_pickup(pickup_address="Jl. Kenanga No. 9, Depok")
        self.make_pickup(status=Status.CANCELLED)

        by_status = self.client.get(CHANGELIST, {"status__exact": Status.PENDING})
        by_search = self.client.get(CHANGELIST, {"q": "kenanga"})

        self.assertEqual(list(by_status.context["cl"].result_list), [pending])
        self.assertEqual(list(by_search.context["cl"].result_list), [pending])
        self.assertContains(by_status, "5,00 kg")

    def test_change_page_shows_items_and_history_but_locks_workflow_fields(self):
        pickup = self.make_pickup()
        response = self.client.get(reverse("admin:pickup_pickuprequest_change", args=[pickup.pk]))

        self.assertEqual(response.status_code, 200)
        readonly = response.context["adminform"].readonly_fields
        for field in ("giver", "collector", "status", "created_at"):
            self.assertIn(field, readonly)
        self.assertContains(response, "Kardus Uji")
        self.assertContains(response, "Riwayat status")

    def test_admin_can_correct_address_and_schedule(self):
        pickup = self.make_pickup()
        url = reverse("admin:pickup_pickuprequest_change", args=[pickup.pk])
        form = self.client.get(url).context["adminform"].form
        data = {name: form[name].value() or "" for name in form.fields}
        data.update({
            "pickup_address": "Jl. Baru No. 1, Tebet, Jakarta Selatan",
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1", "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000",
            "items-0-id": str(pickup.items.get().pk), "items-0-pickup_request": str(pickup.pk),
            "items-0-estimated_weight": "5.00", "items-0-actual_weight": "",
            "status_history-TOTAL_FORMS": "1", "status_history-INITIAL_FORMS": "1",
            "status_history-MIN_NUM_FORMS": "0", "status_history-MAX_NUM_FORMS": "1000",
            "status_history-0-id": str(pickup.status_history.get().pk), "status_history-0-pickup": str(pickup.pk),
        })

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        pickup.refresh_from_db()
        self.assertEqual(pickup.pickup_address, "Jl. Baru No. 1, Tebet, Jakarta Selatan")

    def test_admin_cannot_add_or_delete_pickups(self):
        pickup = self.make_pickup()

        self.assertEqual(self.client.get(reverse("admin:pickup_pickuprequest_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:pickup_pickuprequest_delete", args=[pickup.pk])).status_code, 403)

    def test_cancel_action_cancels_only_cancellable_and_logs_the_admin(self):
        pending = self.make_pickup()
        assigned = self.make_pickup(status=Status.ASSIGNED)
        on_the_way = self.make_pickup(status=Status.ON_THE_WAY)

        response = self.run_action("cancel_pickups", [pending, assigned, on_the_way])

        for pickup in (pending, assigned, on_the_way):
            pickup.refresh_from_db()
        self.assertEqual(pending.status, Status.CANCELLED)
        self.assertEqual(assigned.status, Status.CANCELLED)
        self.assertEqual(on_the_way.status, Status.ON_THE_WAY)
        self.assertEqual(pending.status_history.last().changed_by, self.admin)
        self.assertContains(response, "2 pickup dibatalkan")
        self.assertContains(response, "1 pickup dilewati")

    def test_release_action_puts_assigned_pickups_back_in_the_queue(self):
        assigned = self.make_pickup(status=Status.ASSIGNED)
        pending = self.make_pickup()

        response = self.run_action("release_pickups", [assigned, pending])

        assigned.refresh_from_db()
        self.assertEqual(assigned.status, Status.PENDING)
        self.assertIsNone(assigned.collector)
        self.assertContains(response, "1 pickup dikembalikan ke antrean")
