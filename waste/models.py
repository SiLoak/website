from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator


class WasteType(models.Model):
    category = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=120, unique=True)
    rate_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CollectionPoint(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    operating_hours = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu penimbangan"
        VERIFIED = "verified", "Terverifikasi"
        CANCELED = "canceled", "Dibatalkan"

    class IncentiveAllocation(models.TextChoices):
        WALLET = "wallet", "Terima insentif"
        DONATION = "donation", "Donasikan"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waste_submissions",
    )
    collection_point = models.ForeignKey(
        CollectionPoint,
        on_delete=models.PROTECT,
        related_name="submissions",
    )
    incentive_allocation = models.CharField(
        max_length=12,
        choices=IncentiveAllocation.choices,
        default=IncentiveAllocation.WALLET,
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_waste_submissions",
    )
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Setoran #{self.pk} — {self.get_status_display()}"

    @property
    def estimated_weight(self):
        return sum(
            (item.estimated_weight for item in self.items.all()), Decimal("0")
        )

    @property
    def actual_weight(self):
        items = list(self.items.all())
        if not items or any(item.actual_weight is None for item in items):
            return None
        return sum((item.actual_weight for item in items), Decimal("0"))

    @property
    def estimated_reward(self):
        items = list(self.items.all())
        if any(item.unit_rate_snapshot is None for item in items):
            return None
        return sum((item.estimated_subtotal for item in items), Decimal("0"))

    @property
    def actual_reward(self):
        items = list(self.items.all())
        if not items or any(
            item.actual_weight is None or item.unit_rate_snapshot is None
            for item in items
        ):
            return None
        return sum((item.actual_subtotal for item in items), Decimal("0"))


class SubmissionItem(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="items"
    )
    waste_type = models.ForeignKey(
        WasteType, on_delete=models.PROTECT, related_name="submission_items"
    )
    estimated_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    actual_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_rate_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "waste_type"],
                name="unique_waste_type_per_submission",
            )
        ]

    def __str__(self):
        return f"{self.waste_type} — {self.submission}"

    @property
    def estimated_subtotal(self):
        if self.unit_rate_snapshot is None:
            return None
        return self.estimated_weight * self.unit_rate_snapshot

    @property
    def actual_subtotal(self):
        if self.actual_weight is None or self.unit_rate_snapshot is None:
            return None
        return self.actual_weight * self.unit_rate_snapshot
