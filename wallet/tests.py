from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase, RequestFactory

from wallet.models import (
    Wallet,
    WalletTransaction,
    WithdrawalRequest,
    Donation,
)
from wallet.services import credit_wallet, record_donation
from wallet.views import (
    calculate_withdrawal_fees,
    withdraw_view,
    donation_view,
    wallet_index,
)

from wallet.admin import (
    mark_withdrawals_success,
    mark_withdrawals_failed,
)

from waste.models import (
    CollectionPoint,
    Submission,
    SubmissionItem,
    WasteType,
)
from waste.admin import verify_submissions

User = get_user_model()

class WalletBaseTestCase(TestCase):
    """Setup dasar yang digunakan oleh seluruh pengujian Wallet."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpassword123",
        )

        self.wallet = Wallet.objects.create(
            user=self.user,
            balance=Decimal("50000.00"),
        )

        self.factory = RequestFactory()

    def create_request(self, method="get", path="/wallet/", data=None):
        if method.lower() == "post":
            request = self.factory.post(path, data or {})
        else:
            request = self.factory.get(path)

        request.user = self.user
        return request

    def create_admin_context(self):
        request = self.factory.post("/admin/")
        request.user = self.user

        modeladmin = SimpleNamespace(
            message_user=Mock()
        )

        return modeladmin, request

# WALLET SERVICES
class WalletServiceTests(WalletBaseTestCase):

    def test_credit_wallet_success(self):
        """Insentif menambah saldo dan total earned."""

        wallet, tx = credit_wallet(
            user=self.user,
            amount=Decimal("25000.00"),
            description="Insentif setoran #1",
            reference="waste_submission:1",
        )

        wallet.refresh_from_db()

        self.assertEqual(wallet.balance, Decimal("75000.00"))
        self.assertEqual(wallet.total_earned, Decimal("25000.00"))

        self.assertIsNotNone(tx)
        self.assertEqual(
            tx.transaction_type,
            WalletTransaction.Type.EARNING,
        )
        self.assertEqual(
            tx.status,
            WalletTransaction.Status.SUCCESS,
        )
        self.assertEqual(tx.amount, Decimal("25000.00"))

    def test_credit_wallet_duplicate_reference(self):
        """Insentif tidak boleh tercatat dua kali."""

        credit_wallet(
            self.user,
            Decimal("25000.00"),
            "Insentif setoran #1",
            "waste_submission:1",
        )

        wallet, tx = credit_wallet(
            self.user,
            Decimal("25000.00"),
            "Insentif setoran #1",
            "waste_submission:1",
        )

        wallet.refresh_from_db()

        self.assertEqual(wallet.balance, Decimal("75000.00"))
        self.assertEqual(wallet.total_earned, Decimal("25000.00"))
        self.assertIsNone(tx)

        self.assertEqual(
            WalletTransaction.objects.filter(
                reference="waste_submission:1"
            ).count(),
            1,
        )

    def test_credit_wallet_reject_zero_amount(self):
        """Insentif nol harus ditolak."""

        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            credit_wallet(
                self.user,
                Decimal("0"),
                "Insentif",
            )

    def test_record_donation_success(self):
        """Donasi langsung tidak menambah saldo Wallet."""

        wallet, tx = record_donation(
            user=self.user,
            amount=Decimal("10000.00"),
            description="Donasi insentif setoran #1",
            reference="waste_submission_donation:1",
        )

        wallet.refresh_from_db()

        self.assertEqual(wallet.balance, Decimal("50000.00"))
        self.assertEqual(wallet.total_earned, Decimal("0.00"))
        self.assertEqual(wallet.total_donated, Decimal("10000.00"))

        self.assertEqual(
            tx.transaction_type,
            WalletTransaction.Type.DONATION,
        )
        self.assertEqual(
            tx.status,
            WalletTransaction.Status.SUCCESS,
        )

        self.assertTrue(
            Donation.objects.filter(
                transaction=tx,
                amount=Decimal("10000.00"),
            ).exists()
        )

    def test_record_donation_duplicate_reference(self):
        """Donasi submission tidak boleh tercatat dua kali."""

        record_donation(
            self.user,
            Decimal("10000.00"),
            "Donasi insentif setoran #1",
            "waste_submission_donation:1",
        )

        wallet, tx = record_donation(
            self.user,
            Decimal("10000.00"),
            "Donasi insentif setoran #1",
            "waste_submission_donation:1",
        )

        wallet.refresh_from_db()

        self.assertEqual(wallet.total_donated, Decimal("10000.00"))
        self.assertEqual(
            WalletTransaction.objects.filter(
                reference="waste_submission_donation:1"
            ).count(),
            1,
        )
        self.assertEqual(Donation.objects.count(), 1)
        self.assertIsNotNone(tx)

    def test_record_donation_reject_zero_amount(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            record_donation(
                self.user,
                Decimal("0"),
                "Donasi",
            )

# SUBMISSION VERIFICATION INTEGRATION
class SubmissionWalletIntegrationTests(WalletBaseTestCase):

    def setUp(self):
        super().setUp()

        self.collection_point = CollectionPoint.objects.create(
            name="Drop-off Point UI",
            address="Depok",
        )

        self.waste_type = WasteType.objects.create(
            name="Botol Plastik",
            category="Plastik",
            rate_per_kg=Decimal("5000.00"),
        )

    def create_submission(self, allocation="wallet"):
        submission = Submission.objects.create(
            user=self.user,
            collection_point=self.collection_point,
            incentive_allocation=allocation,
        )

        SubmissionItem.objects.create(
            submission=submission,
            waste_type=self.waste_type,
            estimated_weight=Decimal("2.00"),
            actual_weight=Decimal("3.00"),
        )

        return submission

    def verify(self, submission):
        modeladmin, request = self.create_admin_context()

        verify_submissions(
            modeladmin,
            request,
            Submission.objects.filter(pk=submission.pk),
        )

        return modeladmin

    def test_verified_submission_credits_wallet(self):
        """Submission terverifikasi dengan alokasi Wallet."""

        submission = self.create_submission(
            Submission.IncentiveAllocation.WALLET
        )

        self.verify(submission)

        self.wallet.refresh_from_db()
        submission.refresh_from_db()

        self.assertEqual(
            submission.status,
            Submission.Status.VERIFIED,
        )

        # 3 kg x Rp5.000
        self.assertEqual(self.wallet.balance, Decimal("65000.00"))
        self.assertEqual(
            self.wallet.total_earned,
            Decimal("15000.00"),
        )
        self.assertEqual(
            self.wallet.total_donated,
            Decimal("0.00"),
        )

        self.assertTrue(
            WalletTransaction.objects.filter(
                reference=f"waste_submission:{submission.pk}",
                transaction_type=WalletTransaction.Type.EARNING,
                amount=Decimal("15000.00"),
            ).exists()
        )

    def test_verified_submission_donates_incentive(self):
        """Submission dengan alokasi Donation tidak menambah saldo."""

        submission = self.create_submission(
            Submission.IncentiveAllocation.DONATION
        )

        self.verify(submission)

        self.wallet.refresh_from_db()
        submission.refresh_from_db()

        self.assertEqual(
            submission.status,
            Submission.Status.VERIFIED,
        )

        self.assertEqual(
            self.wallet.balance,
            Decimal("50000.00"),
        )
        self.assertEqual(
            self.wallet.total_earned,
            Decimal("0.00"),
        )
        self.assertEqual(
            self.wallet.total_donated,
            Decimal("15000.00"),
        )

        tx = WalletTransaction.objects.get(
            reference=f"waste_submission_donation:{submission.pk}"
        )

        self.assertEqual(
            tx.transaction_type,
            WalletTransaction.Type.DONATION,
        )
        self.assertEqual(tx.amount, Decimal("15000.00"))

        self.assertTrue(
            Donation.objects.filter(
                transaction=tx,
                amount=Decimal("15000.00"),
            ).exists()
        )

    def test_verified_submission_does_not_duplicate_reward(self):
        """Submission yang sudah diverifikasi tidak diproses ulang."""

        submission = self.create_submission(
            Submission.IncentiveAllocation.WALLET
        )

        self.verify(submission)
        self.verify(submission)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("65000.00"),
        )
        self.assertEqual(
            self.wallet.total_earned,
            Decimal("15000.00"),
        )

        self.assertEqual(
            WalletTransaction.objects.filter(
                reference=f"waste_submission:{submission.pk}"
            ).count(),
            1,
        )

    def test_submission_without_actual_weight_is_not_verified(self):
        """Submission tanpa berat aktual tidak boleh diverifikasi."""

        submission = self.create_submission()

        item = submission.items.first()
        item.actual_weight = None
        item.save()

        self.verify(submission)

        submission.refresh_from_db()
        self.wallet.refresh_from_db()

        self.assertEqual(
            submission.status,
            Submission.Status.PENDING,
        )
        self.assertEqual(self.wallet.balance, Decimal("50000.00"))
        self.assertEqual(WalletTransaction.objects.count(), 0)

# WITHDRAWAL FEE CALCULATION
class WithdrawalFeeTests(TestCase):

    def test_bank_transfer_fee(self):
        transfer_fee, service_fee, total = calculate_withdrawal_fees(
            "bank",
            "BCA",
            Decimal("10000.00"),
        )

        self.assertEqual(transfer_fee, Decimal("2500.00"))
        self.assertEqual(service_fee, Decimal("200"))
        self.assertEqual(total, Decimal("12700.00"))

    def test_bni_has_zero_transfer_fee(self):
        transfer_fee, service_fee, total = calculate_withdrawal_fees(
            "bank",
            "BNI",
            Decimal("10000.00"),
        )

        self.assertEqual(transfer_fee, Decimal("0.00"))
        self.assertEqual(service_fee, Decimal("200"))
        self.assertEqual(total, Decimal("10200.00"))

    def test_ewallet_transfer_fee(self):
        transfer_fee, service_fee, total = calculate_withdrawal_fees(
            "ewallet",
            "DANA",
            Decimal("10000.00"),
        )

        self.assertEqual(transfer_fee, Decimal("500.00"))
        self.assertEqual(service_fee, Decimal("200"))
        self.assertEqual(total, Decimal("10700.00"))

    def test_service_fee_rounding(self):
        _, service_fee, _ = calculate_withdrawal_fees(
            "bank",
            "BNI",
            Decimal("12525.00"),
        )

        # 2% x 12.525 = 250.5, dibulatkan HALF_UP
        self.assertEqual(service_fee, Decimal("251"))

# WITHDRAWAL VIEW
class WithdrawalViewTests(WalletBaseTestCase):

    @patch("wallet.views.messages.success")
    @patch("wallet.views.redirect", return_value=HttpResponse())
    @patch("wallet.views.render", return_value=HttpResponse())
    def test_withdrawal_deducts_amount_and_fees(
        self,
        mock_render,
        mock_redirect,
        mock_message,
    ):
        """Pengajuan withdrawal memotong nominal dan seluruh fee."""

        request = self.create_request(
            method="post",
            path="/wallet/withdraw/",
            data={
                "destination_type": "bank",
                "destination_name": "BNI",
                "account_number": "1234567890",
                "account_holder": "Test User",
                "amount": "10000",
            },
        )

        withdraw_view(request)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("39800.00"),
        )
        self.assertEqual(
            self.wallet.total_withdrawn,
            Decimal("10000.00"),
        )

        withdrawal = WithdrawalRequest.objects.get(
            wallet=self.wallet
        )

        self.assertEqual(
            withdrawal.amount,
            Decimal("10000.00"),
        )
        self.assertEqual(
            withdrawal.transfer_fee,
            Decimal("0.00"),
        )
        self.assertEqual(
            withdrawal.service_fee,
            Decimal("200"),
        )
        self.assertEqual(
            withdrawal.total_deduction,
            Decimal("10200.00"),
        )

        self.assertEqual(
            withdrawal.transaction.status,
            WalletTransaction.Status.PENDING,
        )

    @patch("wallet.views.messages.success")
    @patch("wallet.views.redirect", return_value=HttpResponse())
    @patch("wallet.views.render", return_value=HttpResponse())
    def test_withdrawal_rejected_when_balance_cannot_cover_fees(
        self,
        mock_render,
        mock_redirect,
        mock_message,
    ):
        """Saldo harus cukup untuk nominal dan seluruh biaya."""

        self.wallet.balance = Decimal("10100.00")
        self.wallet.save()

        request = self.create_request(
            method="post",
            path="/wallet/withdraw/",
            data={
                "destination_type": "bank",
                "destination_name": "BNI",
                "account_number": "1234567890",
                "account_holder": "Test User",
                "amount": "10000",
            },
        )

        withdraw_view(request)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("10100.00"),
        )
        self.assertEqual(
            self.wallet.total_withdrawn,
            Decimal("0.00"),
        )
        self.assertEqual(WithdrawalRequest.objects.count(), 0)
        self.assertEqual(WalletTransaction.objects.count(), 0)

# WITHDRAWAL ADMIN ACTIONS
class WithdrawalAdminActionTests(WalletBaseTestCase):

    def create_withdrawal(self):
        tx = WalletTransaction.objects.create(
            wallet=self.wallet,
            transaction_type=WalletTransaction.Type.WITHDRAWAL,
            status=WalletTransaction.Status.PENDING,
            amount=Decimal("10000.00"),
            description="Penarikan saldo",
            destination="BNI ••••7890",
        )

        withdrawal = WithdrawalRequest.objects.create(
            wallet=self.wallet,
            transaction=tx,
            destination_type="bank",
            destination_name="BNI",
            account_number="1234567890",
            account_holder="Test User",
            amount=Decimal("10000.00"),
            transfer_fee=Decimal("0.00"),
            service_fee=Decimal("200.00"),
            total_deduction=Decimal("10200.00"),
        )

        self.wallet.balance = Decimal("39800.00")
        self.wallet.total_withdrawn = Decimal("10000.00")
        self.wallet.save()

        return withdrawal

    def test_mark_withdrawal_success(self):
        """Admin berhasil mengubah status penarikan."""

        withdrawal = self.create_withdrawal()
        modeladmin, request = self.create_admin_context()

        mark_withdrawals_success(
            modeladmin,
            request,
            WithdrawalRequest.objects.filter(pk=withdrawal.pk),
        )

        withdrawal.refresh_from_db()
        withdrawal.transaction.refresh_from_db()

        self.assertEqual(withdrawal.status, "success")
        self.assertEqual(
            withdrawal.transaction.status,
            WalletTransaction.Status.SUCCESS,
        )

        self.wallet.refresh_from_db()

        # Saldo tidak berubah lagi saat status menjadi success.
        self.assertEqual(
            self.wallet.balance,
            Decimal("39800.00"),
        )

    def test_mark_withdrawal_failed_refunds_balance(self):
        """Admin gagal memproses penarikan dan mengembalikan saldo."""

        withdrawal = self.create_withdrawal()
        modeladmin, request = self.create_admin_context()

        mark_withdrawals_failed(
            modeladmin,
            request,
            WithdrawalRequest.objects.filter(pk=withdrawal.pk),
        )

        withdrawal.refresh_from_db()
        withdrawal.transaction.refresh_from_db()
        self.wallet.refresh_from_db()

        self.assertEqual(withdrawal.status, "failed")
        self.assertEqual(
            withdrawal.transaction.status,
            WalletTransaction.Status.FAILED,
        )

        self.assertEqual(
            self.wallet.balance,
            Decimal("50000.00"),
        )
        self.assertEqual(
            self.wallet.total_withdrawn,
            Decimal("0.00"),
        )

        refund = WalletTransaction.objects.get(
            reference=f"withdrawal_refund:{withdrawal.pk}"
        )

        self.assertEqual(
            refund.transaction_type,
            WalletTransaction.Type.REFUND,
        )
        self.assertEqual(
            refund.amount,
            Decimal("10200.00"),
        )
        self.assertEqual(
            refund.status,
            WalletTransaction.Status.SUCCESS,
        )

    def test_failed_withdrawal_cannot_be_refunded_twice(self):
        """Action refund kedua tidak boleh menambah saldo lagi."""

        withdrawal = self.create_withdrawal()
        modeladmin, request = self.create_admin_context()

        queryset = WithdrawalRequest.objects.filter(pk=withdrawal.pk)

        mark_withdrawals_failed(modeladmin, request, queryset)
        mark_withdrawals_failed(modeladmin, request, queryset)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("50000.00"),
        )
        self.assertEqual(
            WalletTransaction.objects.filter(
                transaction_type=WalletTransaction.Type.REFUND
            ).count(),
            1,
        )

# DONATION FROM WALLET
class WalletDonationViewTests(WalletBaseTestCase):

    @patch("wallet.views.messages.success")
    @patch("wallet.views.redirect", return_value=HttpResponse())
    @patch("wallet.views.render", return_value=HttpResponse())
    def test_donation_deducts_wallet_balance(
        self,
        mock_render,
        mock_redirect,
        mock_message,
    ):
        """Donasi dari Wallet mengurangi saldo dan menambah total donasi."""

        request = self.create_request(
            method="post",
            path="/wallet/donate/",
            data={
                "amount": "5000",
                "message": "Semoga bermanfaat.",
            },
        )

        donation_view(request)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("45000.00"),
        )
        self.assertEqual(
            self.wallet.total_donated,
            Decimal("5000.00"),
        )
        self.assertEqual(
            self.wallet.total_earned,
            Decimal("0.00"),
        )

        tx = WalletTransaction.objects.get(
            transaction_type=WalletTransaction.Type.DONATION
        )

        self.assertEqual(tx.amount, Decimal("5000.00"))
        self.assertEqual(
            tx.status,
            WalletTransaction.Status.SUCCESS,
        )
        self.assertEqual(tx.description, "Donasi saldo")

        donation = Donation.objects.get(transaction=tx)

        self.assertEqual(donation.amount, Decimal("5000.00"))
        self.assertEqual(donation.message, "Semoga bermanfaat.")

    @patch("wallet.views.messages.success")
    @patch("wallet.views.redirect", return_value=HttpResponse())
    @patch("wallet.views.render", return_value=HttpResponse())
    def test_donation_rejected_when_balance_insufficient(
        self,
        mock_render,
        mock_redirect,
        mock_message,
    ):
        """Donasi tidak boleh melebihi saldo."""

        request = self.create_request(
            method="post",
            path="/wallet/donate/",
            data={
                "amount": "60000",
                "message": "Test",
            },
        )

        donation_view(request)

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance,
            Decimal("50000.00"),
        )
        self.assertEqual(
            self.wallet.total_donated,
            Decimal("0.00"),
        )
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(WalletTransaction.objects.count(), 0)

# WALLET TRANSACTION HISTORY
class WalletTransactionHistoryTests(WalletBaseTestCase):

    @patch("wallet.views.render", return_value=HttpResponse())
    def test_wallet_index_displays_user_transactions(self, mock_render):
        """History Wallet hanya mengambil transaksi milik user."""

        WalletTransaction.objects.create(
            wallet=self.wallet,
            transaction_type=WalletTransaction.Type.EARNING,
            status=WalletTransaction.Status.SUCCESS,
            amount=Decimal("10000.00"),
            description="Insentif setoran",
        )

        request = self.create_request()
        wallet_index(request)

        context = mock_render.call_args.args[2]

        self.assertEqual(context["wallet"], self.wallet)
        self.assertEqual(context["transactions"].count(), 1)
        self.assertFalse(context["preview_mode"])

    @patch("wallet.views.render", return_value=HttpResponse())
    def test_transaction_history_contains_all_transaction_types(
        self,
        mock_render,
    ):
        """History dapat menyimpan earning, withdrawal, donation, refund."""

        transaction_types = [
            WalletTransaction.Type.EARNING,
            WalletTransaction.Type.WITHDRAWAL,
            WalletTransaction.Type.DONATION,
            WalletTransaction.Type.REFUND,
        ]

        for transaction_type in transaction_types:
            WalletTransaction.objects.create(
                wallet=self.wallet,
                transaction_type=transaction_type,
                status=WalletTransaction.Status.SUCCESS,
                amount=Decimal("1000.00"),
                description=f"Test {transaction_type}",
            )

        request = self.create_request()
        wallet_index(request)

        context = mock_render.call_args.args[2]
        transactions = list(context["transactions"])

        displayed_types = {
            tx.transaction_type for tx in transactions
        }

        self.assertEqual(
            displayed_types,
            set(transaction_types),
        )

    def test_user_cannot_access_another_users_transaction(self):
        """User tidak boleh membuka detail transaksi milik user lain."""

        from django.http import Http404
        from wallet.views import transaction_detail

        another_user = User.objects.create_user(
            username="anotheruser",
            password="testpassword123",
        )

        another_wallet = Wallet.objects.create(
            user=another_user,
        )

        tx = WalletTransaction.objects.create(
            wallet=another_wallet,
            transaction_type=WalletTransaction.Type.EARNING,
            status=WalletTransaction.Status.SUCCESS,
            amount=Decimal("10000.00"),
            description="Transaksi user lain",
        )

        request = self.create_request(
            path=f"/wallet/transactions/{tx.pk}/"
        )

        with self.assertRaises(Http404):
            transaction_detail(request, tx.pk)