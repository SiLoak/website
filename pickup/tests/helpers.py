from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from pickup.models import PickupItem, PickupRequest, PickupStatusHistory
from waste.models import WasteType

Status = PickupRequest.Status
TEST_PASSWORD = "unused-test-pass"


class PickupTestCase(TestCase):
    """Users, a waste type, and helpers to build pickups in a given state."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.giver = User.objects.create_user("giver", password=TEST_PASSWORD, first_name="Gita")
        self.other_giver = User.objects.create_user("other-giver", password=TEST_PASSWORD)
        collectors = Group.objects.get_or_create(name="Collector")[0]
        self.collector = User.objects.create_user("collector", password=TEST_PASSWORD, first_name="Kurir")
        self.collector.groups.add(collectors)
        self.other_collector = User.objects.create_user("collector-2", password=TEST_PASSWORD)
        self.other_collector.groups.add(collectors)
        # New accounts join Giver automatically (auth/signals.py); collector
        # accounts in these tests are collector-only.
        givers = Group.objects.get(name="Giver")
        self.collector.groups.remove(givers)
        self.other_collector.groups.remove(givers)
        self.admin = User.objects.create_user("admin", password=TEST_PASSWORD, is_staff=True)
        self.waste_type = WasteType.objects.create(name="Kardus Uji", rate_per_kg=Decimal("2000.00"))
        self.other_type = WasteType.objects.create(name="Botol Uji", rate_per_kg=Decimal("3000.00"))

    def make_pickup(self, *, giver=None, status=Status.PENDING, collector=None, weight="5.00",
                    actual_weight=None, allocation="wallet", **fields):
        defaults = {
            "pickup_address": "Jl. Mawar No. 12, Pasar Minggu, Jakarta Selatan",
            "address_detail": "Pagar hitam",
            "contact_phone": "081234567890",
            "scheduled_date": timezone.localdate() + timedelta(days=1),
            "time_slot": PickupRequest.TimeSlot.S1012,
            "incentive_allocation": allocation,
        }
        defaults.update(fields)
        if status not in (Status.PENDING, Status.CANCELLED, Status.FAILED) and collector is None:
            collector = self.collector
        pickup = PickupRequest.objects.create(
            giver=giver or self.giver, status=status, collector=collector, **defaults
        )
        PickupItem.objects.create(
            pickup_request=pickup,
            waste_type=self.waste_type,
            estimated_weight=Decimal(weight),
            actual_weight=Decimal(actual_weight) if actual_weight else None,
            unit_rate_snapshot=self.waste_type.rate_per_kg,
        )
        PickupStatusHistory.objects.create(pickup=pickup, new_status=status, changed_by=pickup.giver)
        return pickup

    def pickup_payload(self, **overrides):
        data = {
            "delivery_method": "minta_dijemput",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "6",
            "items-0-waste_type": str(self.waste_type.pk),
            "items-0-estimated_weight": "4.50",
            "pickup_address": "Jl. Melati No. 3, Tebet, Jakarta Selatan",
            "address_detail": "Rumah cat biru",
            "contact_phone": "0812 3456 7890",
            "courier_note": "Tekan bel",
            "latitude": "-6.226000",
            "longitude": "106.853000",
            "pickup_date_option": "tomorrow",
            "time_slot": "10:00-12:00",
            "incentive_allocation": "wallet",
        }
        data.update(overrides)
        return data
