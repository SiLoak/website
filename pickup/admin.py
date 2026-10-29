from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from pickup.models import PickupItem, PickupRequest, PickupStatusHistory
from wallet.services import credit_wallet, record_donation
from waste.models import Submission


class PickupItemInline(admin.TabularInline):
    model = PickupItem
    extra = 0
    can_delete = False
    fields = ("waste_type", "estimated_weight", "actual_weight", "unit_rate_snapshot")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class PickupStatusHistoryInline(admin.TabularInline):
    model = PickupStatusHistory
    extra = 0
    can_delete = False
    fields = ("previous_status", "new_status", "changed_by", "note", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Verifikasi pickup selesai dan proses insentif")
def verify_pickups(modeladmin, request, queryset):
    verified_count = 0
    missing_weight_count = 0
    missing_rate_count = 0
    invalid_reward_count = 0

    for selected in queryset.filter(
        status=PickupRequest.Status.COMPLETED,
        verified_at__isnull=True,
    ):
        with transaction.atomic():
            pickup = (
                PickupRequest.objects.select_for_update()
                .select_related("giver")
                .get(pk=selected.pk)
            )
            if (
                pickup.status != PickupRequest.Status.COMPLETED
                or pickup.verified_at is not None
            ):
                continue

            items = list(pickup.items.select_related("waste_type"))
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
                    PickupItem.objects.bulk_update(
                        snapshot_updates, ["unit_rate_snapshot"]
                    )

                pickup.verified_at = timezone.now()
                pickup.verified_by = request.user
                pickup.save(update_fields=["verified_at", "verified_by", "updated_at"])
                PickupStatusHistory.objects.create(
                    pickup=pickup,
                    previous_status=PickupRequest.Status.COMPLETED,
                    new_status=PickupRequest.Status.COMPLETED,
                    changed_by=request.user,
                    note="Hasil timbang dan insentif diverifikasi admin.",
                )

                if pickup.incentive_allocation == Submission.IncentiveAllocation.WALLET:
                    credit_wallet(
                        user=pickup.giver,
                        amount=actual_reward,
                        description=f"Insentif pickup #{pickup.pk}",
                        reference=f"pickup:{pickup.pk}",
                    )
                else:
                    record_donation(
                        user=pickup.giver,
                        amount=actual_reward,
                        description=f"Donasi insentif pickup #{pickup.pk}",
                        reference=f"pickup_donation:{pickup.pk}",
                    )
                verified_count += 1

    if verified_count:
        modeladmin.message_user(
            request,
            f"{verified_count} pickup diverifikasi dan insentif diproses.",
            messages.SUCCESS,
        )
    if missing_weight_count:
        modeladmin.message_user(
            request,
            f"{missing_weight_count} pickup dilewati karena berat aktual belum lengkap.",
            messages.WARNING,
        )
    if missing_rate_count:
        modeladmin.message_user(
            request,
            f"{missing_rate_count} pickup dilewati karena tarif jenis sampah belum diatur.",
            messages.WARNING,
        )
    if invalid_reward_count:
        modeladmin.message_user(
            request,
            f"{invalid_reward_count} pickup dilewati karena total insentif harus lebih dari nol.",
            messages.WARNING,
        )
    if not any((verified_count, missing_weight_count, missing_rate_count, invalid_reward_count)):
        modeladmin.message_user(
            request,
            "Tidak ada pickup selesai yang menunggu verifikasi pada pilihan ini.",
            messages.INFO,
        )


@admin.register(PickupRequest)
class PickupRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "giver",
        "collector",
        "status",
        "scheduled_date",
        "completed_at",
        "verified_at",
    )
    list_filter = ("status", "scheduled_date", "incentive_allocation")
    search_fields = ("=id", "giver__username", "giver__email", "collector__username")
    readonly_fields = tuple(field.name for field in PickupRequest._meta.fields)
    inlines = (PickupItemInline, PickupStatusHistoryInline)
    actions = (verify_pickups,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
