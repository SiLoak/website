from decimal import Decimal

from pickup import services
from wallet.models import Donation, Wallet, WalletTransaction

from .helpers import PickupTestCase, Status


class PickupIncentiveTests(PickupTestCase):
    def complete(self, pickup):
        return services.change_status(pickup.pk, Status.COMPLETED, self.collector)

    def test_completing_a_pickup_credits_the_actual_reward_to_the_wallet(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="4.00")
        self.complete(pickup)

        wallet = Wallet.objects.get(user=self.giver)
        self.assertEqual(wallet.balance, Decimal("8000.00"))
        tx = WalletTransaction.objects.get(wallet=wallet, transaction_type="earning")
        self.assertEqual(tx.reference, f"pickup:{pickup.pk}")

    def test_donation_allocation_records_a_donation_instead_of_balance(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="2.50", allocation="donation")
        self.complete(pickup)

        wallet = Wallet.objects.get(user=self.giver)
        self.assertEqual(wallet.balance, Decimal("0"))
        self.assertEqual(Donation.objects.get(wallet=wallet).amount, Decimal("5000.00"))

    def test_incentive_is_credited_only_once_per_pickup(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="1.00")
        self.complete(pickup)
        services.credit_pickup_incentive(pickup)

        self.assertEqual(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").count(), 1)

    def test_pickup_without_a_priced_reward_completes_without_crediting(self):
        pickup = self.make_pickup(status=Status.WEIGHING, actual_weight="1.00")
        pickup.items.update(unit_rate_snapshot=None)
        self.complete(pickup)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, Status.COMPLETED)
        self.assertFalse(WalletTransaction.objects.filter(reference=f"pickup:{pickup.pk}").exists())
