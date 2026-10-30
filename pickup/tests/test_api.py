from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from pickup.models import PickupRequest

from .helpers import PickupTestCase, Status


class GiverPickupApiTests(PickupTestCase):
    url = reverse("pickup:get_pickup_json")

    def test_lists_only_the_givers_pickups(self):
        mine = self.make_pickup()
        self.make_pickup(giver=self.other_giver)
        self.client.force_login(self.giver)

        data = self.client.get(self.url).json()

        self.assertEqual([row["pk"] for row in data], [str(mine.pk)])
        self.assertEqual(data[0]["fields"]["address"], mine.pickup_address)

    def test_filters_by_status_and_exact_id(self):
        pending = self.make_pickup()
        self.make_pickup(status=Status.CANCELLED)
        self.client.force_login(self.giver)

        self.assertEqual(len(self.client.get(self.url, {"status": Status.PENDING}).json()), 1)
        self.assertEqual(self.client.get(self.url, {"status": "BOGUS"}).json(), [])
        self.assertEqual(self.client.get(self.url, {"q": str(pending.pk)}).json()[0]["pk"], str(pending.pk))
        self.assertEqual(self.client.get(self.url, {"q": "not-a-uuid"}).json(), [])

    def test_requires_login_and_giver_role(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class CollectorPickupApiTests(PickupTestCase):
    url = reverse("pickup:get_collector_pickup_json")

    def test_mine_scope_lists_assigned_pickups(self):
        assigned = self.make_pickup(status=Status.ASSIGNED)
        self.make_pickup(status=Status.ASSIGNED, collector=self.other_collector)
        self.client.force_login(self.collector)

        data = self.client.get(self.url).json()

        self.assertEqual([row["pk"] for row in data], [str(assigned.pk)])
        self.assertEqual(data[0]["fields"]["giver_name"], "Gita")

    def test_available_scope_lists_unassigned_pending_pickups(self):
        open_pickup = self.make_pickup()
        self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)

        data = self.client.get(self.url, {"scope": "available"}).json()

        self.assertEqual([row["pk"] for row in data], [str(open_pickup.pk)])

    def test_rejects_unknown_scope_and_non_collectors(self):
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(self.url, {"scope": "all"}).status_code, 400)
        self.client.force_login(self.giver)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_collector_dashboard_page_is_for_collectors_only(self):
        page = reverse("pickup:show_collector_pickup_list")
        self.client.force_login(self.giver)
        self.assertEqual(self.client.get(page).status_code, 403)
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(page).status_code, 200)


class PickupDetailAccessTests(PickupTestCase):
    def detail_json(self, pickup):
        return self.client.get(reverse("pickup:get_pickup_detail_json", args=[pickup.pk]))

    def test_owner_sees_contact_history_and_cancel_flag(self):
        pickup = self.make_pickup(latitude="-6.2", longitude="106.8")
        self.client.force_login(self.giver)

        data = self.detail_json(pickup).json()

        self.assertEqual(data["fields"]["contact_phone"], "081234567890")
        self.assertTrue(data["fields"]["is_cancellable"])
        self.assertEqual(data["fields"]["latitude"], -6.2)
        self.assertEqual(data["history"][0]["new_status"], Status.PENDING)

    def test_collector_sees_open_pickup_without_contact(self):
        pickup = self.make_pickup()
        self.client.force_login(self.collector)

        data = self.detail_json(pickup).json()

        self.assertIsNone(data["fields"]["contact_phone"])
        self.assertFalse(data["fields"]["is_cancellable"])

    def test_strangers_get_404_not_403_so_ids_do_not_leak(self):
        pickup = self.make_pickup()
        self.client.force_login(self.other_giver)

        self.assertEqual(self.detail_json(pickup).status_code, 404)
        self.assertEqual(self.client.get(reverse("pickup:show_pickup_detail", args=[pickup.pk])).status_code, 404)

    def test_other_collectors_cannot_open_an_assigned_pickup(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.other_collector)

        self.assertEqual(self.detail_json(pickup).status_code, 404)

    def test_admin_can_open_any_pickup(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.admin)

        self.assertEqual(self.detail_json(pickup).status_code, 200)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.detail_json(self.make_pickup()).status_code, 401)

    def test_assigned_collector_sees_actions_and_weighing_form(self):
        pickup = self.make_pickup(status=Status.WEIGHING)
        self.client.force_login(self.collector)

        response = self.client.get(reverse("pickup:show_pickup_detail", args=[pickup.pk]))

        self.assertIsNotNone(response.context["weighing_formset"])
        self.assertTrue(response.context["collector_actions"])


class PickupActionApiTests(PickupTestCase):
    def post(self, name, pickup, data=None):
        return self.client.post(reverse(name, args=[pickup.pk]), data or {})

    def test_create_pickup_json_endpoint(self):
        self.client.force_login(self.giver)
        response = self.client.post(reverse("pickup:create_pickup_ajax"), self.pickup_payload())

        self.assertEqual(response.status_code, 201)
        pickup = PickupRequest.objects.get(pk=response.json()["pk"])
        self.assertEqual(pickup.giver, self.giver)
        self.assertEqual(pickup.status_history.count(), 1)

    def test_create_pickup_json_endpoint_reports_errors(self):
        self.client.force_login(self.giver)
        response = self.client.post(reverse("pickup:create_pickup_ajax"), self.pickup_payload(contact_phone="x"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("contact_phone", response.json()["errors"])

    def test_create_pickup_is_rate_limited(self):
        self.client.force_login(self.giver)
        codes = [self.client.post(reverse("pickup:create_pickup_ajax"), {}).status_code for _ in range(6)]

        self.assertEqual(codes[:5], [400] * 5)
        self.assertEqual(codes[5], 429)

    def test_full_collector_flow_from_accept_to_completed(self):
        pickup = self.make_pickup()
        self.client.force_login(self.collector)

        self.assertEqual(self.post("pickup:accept_pickup_ajax", pickup).json()["status"], Status.ASSIGNED)
        for status in (Status.ON_THE_WAY, Status.ARRIVED, Status.WEIGHING):
            self.assertEqual(self.post("pickup:update_pickup_status_ajax", pickup, {"status": status}).status_code, 200)
        item = pickup.items.get()
        response = self.post("pickup:complete_weighing_ajax", pickup, {
            "weigh-TOTAL_FORMS": "1", "weigh-INITIAL_FORMS": "1",
            "weigh-0-id": str(item.pk), "weigh-0-actual_weight": "4.20",
        })

        self.assertEqual(response.json()["status"], Status.COMPLETED)
        pickup.refresh_from_db()
        self.assertIsNotNone(pickup.completed_at)
        self.assertIsNotNone(pickup.verified_at)
        # created, assigned, on the way, arrived, weighing, completed, verified
        self.assertEqual(pickup.status_history.count(), 7)

    def test_collector_can_release_an_assignment_back_to_pending(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)

        self.post("pickup:update_pickup_status_ajax", pickup, {"status": Status.PENDING})

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.PENDING)
        self.assertIsNone(pickup.collector)

    def test_failing_requires_a_reason(self):
        pickup = self.make_pickup(status=Status.ON_THE_WAY)
        self.client.force_login(self.collector)

        missing = self.post("pickup:update_pickup_status_ajax", pickup, {"status": Status.FAILED})
        given = self.post("pickup:update_pickup_status_ajax", pickup, {"status": Status.FAILED, "note": "Rumah kosong"})

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(given.status_code, 200)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status_reason, "Rumah kosong")

    def test_invalid_transitions_and_targets_are_rejected(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.collector)

        skip = self.post("pickup:update_pickup_status_ajax", pickup, {"status": Status.COMPLETED})
        bogus = self.post("pickup:update_pickup_status_ajax", pickup, {"status": "CANCELLED"})

        # Completion only happens through weighing, never via the status endpoint.
        self.assertEqual(skip.status_code, 400)
        self.assertEqual(bogus.status_code, 400)

    def test_other_collector_cannot_move_someone_elses_pickup(self):
        pickup = self.make_pickup(status=Status.ASSIGNED)
        self.client.force_login(self.other_collector)

        response = self.post("pickup:update_pickup_status_ajax", pickup, {"status": Status.ON_THE_WAY})

        self.assertEqual(response.status_code, 403)

    def test_giver_cannot_cancel_someone_elses_pickup(self):
        pickup = self.make_pickup()
        self.client.force_login(self.other_giver)

        self.assertEqual(self.post("pickup:cancel_pickup_ajax", pickup).status_code, 403)

    def test_cancel_after_collector_left_is_refused(self):
        pickup = self.make_pickup(status=Status.ON_THE_WAY)
        self.client.force_login(self.giver)

        self.assertEqual(self.post("pickup:cancel_pickup_ajax", pickup).status_code, 409)

    def test_only_collectors_accept_and_only_once(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)
        self.assertEqual(self.post("pickup:accept_pickup_ajax", pickup).status_code, 403)

        self.client.force_login(self.collector)
        self.post("pickup:accept_pickup_ajax", pickup)
        self.client.force_login(self.other_collector)
        self.assertEqual(self.post("pickup:accept_pickup_ajax", pickup).status_code, 409)

    def test_weighing_guards(self):
        pickup = self.make_pickup(status=Status.ARRIVED)
        self.client.force_login(self.other_collector)
        self.assertEqual(self.post("pickup:complete_weighing_ajax", pickup).status_code, 403)

        self.client.force_login(self.collector)
        self.assertEqual(self.post("pickup:complete_weighing_ajax", pickup).status_code, 400)

    def test_weighing_with_missing_weight_returns_field_errors(self):
        pickup = self.make_pickup(status=Status.WEIGHING)
        item = pickup.items.get()
        self.client.force_login(self.collector)

        response = self.post("pickup:complete_weighing_ajax", pickup, {
            "weigh-TOTAL_FORMS": "1", "weigh-INITIAL_FORMS": "1",
            "weigh-0-id": str(item.pk), "weigh-0-actual_weight": "",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("actual_weight", response.json()["form_errors"][0])

    def test_actions_require_post(self):
        pickup = self.make_pickup()
        self.client.force_login(self.giver)

        self.assertEqual(self.client.get(reverse("pickup:cancel_pickup_ajax", args=[pickup.pk])).status_code, 405)


class PickupFormValidationTests(PickupTestCase):
    def post_form(self, **overrides):
        self.client.force_login(self.giver)
        response = self.client.post(reverse("waste:new"), self.pickup_payload(**overrides))
        return response.context["pickup_form"].errors if response.status_code == 200 else {}

    def test_custom_date_must_be_given_in_range(self):
        today = timezone.localdate()
        self.assertIn("custom_date", self.post_form(pickup_date_option="custom"))
        self.assertIn("custom_date", self.post_form(pickup_date_option="custom", custom_date=(today - timedelta(days=1)).isoformat()))
        self.assertIn("custom_date", self.post_form(pickup_date_option="custom", custom_date=(today + timedelta(days=31)).isoformat()))
        self.assertEqual(self.post_form(pickup_date_option="custom", custom_date=(today + timedelta(days=5)).isoformat()), {})

    def test_custom_date_round_trips_into_the_edit_form(self):
        pickup = self.make_pickup(scheduled_date=timezone.localdate() + timedelta(days=9))
        self.client.force_login(self.giver)

        form = self.client.get(reverse("pickup:edit", args=[pickup.pk])).context["pickup_form"]

        self.assertEqual(form["pickup_date_option"].value(), "custom")
        self.assertEqual(form["custom_date"].value(), pickup.scheduled_date)

    def test_contact_phone_is_normalised(self):
        self.post_form(contact_phone="+62 812-3456-7890")

        self.assertEqual(PickupRequest.objects.get(giver=self.giver).contact_phone, "081234567890")

    def test_address_and_landmark_must_be_descriptive(self):
        errors = self.post_form(pickup_address="Jl. A", address_detail="x")

        self.assertIn("pickup_address", errors)
        self.assertIn("address_detail", errors)

    def test_coordinates_must_be_valid_and_paired(self):
        self.assertIn("latitude", self.post_form(latitude="95"))
        self.assertIn("__all__", self.post_form(longitude=""))

    def test_today_slot_that_already_started_is_rejected(self):
        errors = self.post_form(pickup_date_option="today", time_slot="08:00-10:00")
        now = timezone.localtime().time()
        if now.hour >= 8:
            self.assertIn("time_slot", errors)
        else:
            self.assertEqual(errors, {})
