from decimal import Decimal

from django.contrib import admin, messages
from django.utils import timezone
from django.db import transaction

from .models import CollectionPoint, Submission, SubmissionItem, WasteType
from wallet.services import credit_wallet, record_donation


@admin.register(WasteType)
class WasteTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "rate_per_kg", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "category")


@admin.register(CollectionPoint)
class CollectionPointAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "operating_hours", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address")


class SubmissionItemInline(admin.TabularInline):
    model = SubmissionItem
    extra = 0
    fields = (
        "waste_type",
        "estimated_weight",
        "actual_weight",
        "unit_rate_snapshot",
    )
    readonly_fields = ("estimated_weight", "unit_rate_snapshot")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != Submission.Status.PENDING:
            return (*self.readonly_fields, "actual_weight", "waste_type")
        return self.readonly_fields


@admin.action(description="Verifikasi submission yang sudah ditimbang")
def verify_submissions(modeladmin, request, queryset):
    pending_submissions = queryset.filter(status=Submission.Status.PENDING)
    verified_count = 0
    missing_weight_count = 0
    missing_rate_count = 0
    invalid_reward_count = 0

    for submission in pending_submissions:
        with transaction.atomic():
            submission = Submission.objects.select_for_update().get(pk=submission.pk)

            if submission.status != Submission.Status.PENDING:
                continue

            items = list(submission.items.select_related("waste_type"))

            if not items or any(item.actual_weight is None for item in items):
                missing_weight_count += 1
                continue

            snapshot_updates = []
            for item in items:
                if item.unit_rate_snapshot is not None:
                    continue
                if item.waste_type.rate_per_kg is None:
                    missing_rate_count += 1
                    break
                item.unit_rate_snapshot = item.waste_type.rate_per_kg
                snapshot_updates.append(item)
            else:
                actual_reward = sum(
                    (
                        item.actual_weight * item.unit_rate_snapshot
                        for item in items
                    ),
                    Decimal("0"),
                )

                if actual_reward <= 0:
                    invalid_reward_count += 1
                    continue

                if snapshot_updates:
                    SubmissionItem.objects.bulk_update(
                        snapshot_updates, ["unit_rate_snapshot"]
                    )

                submission.status = Submission.Status.VERIFIED
                submission.verified_at = timezone.now()
                submission.verified_by = request.user
                submission.save(
                    update_fields=["status", "verified_at", "verified_by", "updated_at"]
                )

                if submission.incentive_allocation == Submission.IncentiveAllocation.WALLET:
                    credit_wallet(
                        user=submission.user,
                        amount=actual_reward,
                        description=f"Insentif setoran #{submission.pk}",
                        reference=f"waste_submission:{submission.pk}",
                    )
                elif submission.incentive_allocation == Submission.IncentiveAllocation.DONATION:
                    record_donation(
                        user=submission.user,
                        amount=actual_reward,
                        description=f"Donasi insentif setoran #{submission.pk}",
                        reference=f"waste_submission_donation:{submission.pk}",
                    )

                verified_count += 1
                continue

    if verified_count:
        modeladmin.message_user(
            request,
            f"{verified_count} pengajuan berhasil diverifikasi.",
            messages.SUCCESS,
        )
    if missing_weight_count:
        modeladmin.message_user(
            request,
            f"{missing_weight_count} pengajuan dilewati karena berat aktual belum lengkap.",
            messages.WARNING,
        )
    if missing_rate_count:
        modeladmin.message_user(
            request,
            f"{missing_rate_count} pengajuan dilewati karena tarif jenis sampah belum diatur. Atur tarif di Waste → Waste types, lalu jalankan verifikasi kembali.",
            messages.WARNING,
        )
    if invalid_reward_count:
        modeladmin.message_user(
            request,
            f"{invalid_reward_count} pengajuan dilewati karena total insentif harus lebih dari nol.",
            messages.WARNING,
        )

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "collection_point",
        "status",
        "created_at",
        "verified_at",
    )
    list_filter = ("status", "collection_point", "created_at")
    search_fields = ("=id", "user__username", "user__email", "collection_point__name")
    readonly_fields = (
        "user",
        "created_at",
        "updated_at",
        "verified_at",
        "verified_by",
        "canceled_at",
        "incentive_allocation",
    )
    inlines = (SubmissionItemInline,)
    actions = (verify_submissions,)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return (
            "user",
            "collection_point",
            "status",
            "created_at",
            "updated_at",
            "verified_at",
            "verified_by",
            "canceled_at",
            "incentive_allocation",
        )
