from decimal import Decimal

from pickup import services
from wallet.models import Donation, Wallet, WalletTransaction

from .helpers import PickupTestCase, Status


class PickupIncentiveTests(PickupTestCase):
    """Incentives are paid when a completed pickup is verified (services.verify_completed_pickup)."""

    def complete_and_verify(self, pickup):
        services.change_status(pickup.pk, Status.COMPLETED, self.collector)
        return services.verify_completed_pickup(pickup.pk, self.collector)

    def test_completing_alone_does_not_pay_until_verified(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="4.00")
        services.change_status(pickup.pk, Status.COMPLETED, self.collector)

        self.assertFalse(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").exists())

    def test_verification_credits_the_actual_reward_to_the_wallet(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="4.00")
        self.complete_and_verify(pickup)

        wallet = Wallet.objects.get(user=self.giver)
        self.assertEqual(wallet.balance, Decimal("8000.00"))
        self.assertTrue(WalletTransaction.objects.filter(wallet=wallet, reference=f"pickup:{pickup.pk}").exists())

    def test_donation_allocation_records_a_donation_instead_of_balance(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="2.50", allocation="donation")
        self.complete_and_verify(pickup)

        wallet = Wallet.objects.get(user=self.giver)
        self.assertEqual(wallet.balance, Decimal("0"))
        self.assertEqual(Donation.objects.get(wallet=wallet).amount, Decimal("5000.00"))

    def test_verifying_twice_pays_once(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="1.00")
        self.complete_and_verify(pickup)
        services.verify_completed_pickup(pickup.pk, self.collector)

        self.assertEqual(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").count(), 1)

    def test_missing_rate_blocks_verification(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="1.00")
        pickup.items.update(unit_rate_snapshot=None)
        self.waste_type.rate_per_kg = None
        self.waste_type.save()
        services.change_status(pickup.pk, Status.COMPLETED, self.collector)

        with self.assertRaises(services.PickupServiceError) as caught:
            services.verify_completed_pickup(pickup.pk, self.collector)
        self.assertEqual(caught.exception.code, "missing_rate")
