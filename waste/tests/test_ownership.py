from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from waste.models import CollectionPoint, Submission, SubmissionItem, WasteType


class SubmissionOwnershipTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="secret"
        )
        self.intruder = User.objects.create_user(
            username="intruder", email="intruder@example.com", password="secret"
        )
        self.waste_type = WasteType.objects.create(
            name="Kardus Lama", rate_per_kg=Decimal("5000.00")
        )
        self.point = CollectionPoint.objects.create(
            name="Depo Pasar Minggu",
            address="Jl. Raya Pasar Minggu No. 14",
            operating_hours="08.00 - 16.00 WIB",
        )
        self.submission = Submission.objects.create(
            user=self.owner,
            collection_point=self.point,
            status=Submission.Status.PENDING,
        )
        SubmissionItem.objects.create(
            submission=self.submission,
            waste_type=self.waste_type,
            estimated_weight=Decimal("2.50"),
            unit_rate_snapshot=self.waste_type.rate_per_kg,
        )

    def test_non_owner_cannot_cancel_someone_elses_submission(self):
        self.client.force_login(self.intruder)

        self.client.post(
            reverse("waste:cancel", kwargs={"submission_id": self.submission.pk})
        )

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Submission.Status.PENDING)