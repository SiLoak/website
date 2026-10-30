from django.contrib import admin, messages
from django.db.models import Sum

from pickup import services
from pickup.models import PickupItem, PickupRequest, PickupStatusHistory

Status = PickupRequest.Status


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
    verbose_name_plural = "Riwayat status"
    extra = 0
    can_delete = False
    fields = ("created_at", "previous_status", "new_status", "changed_by", "note")
    readonly_fields = fields
    ordering = ("created_at",)

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
        try:
            services.verify_completed_pickup(
                selected.pk,
                request.user,
                note="Hasil timbang dan insentif diverifikasi admin.",
            )
        except services.PickupServiceError as error:
            if error.code == "missing_weight":
                missing_weight_count += 1
            elif error.code == "missing_rate":
                missing_rate_count += 1
            elif error.code == "invalid_reward":
                invalid_reward_count += 1
            continue
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


def _run_transition(modeladmin, request, queryset, new_status, allowed, reason, done_label):
    changed, skipped = 0, 0
    for pickup in queryset:
        if pickup.status not in allowed:
            skipped += 1
            continue
        try:
            services.change_status(pickup.pk, new_status, request.user, reason=reason)
            changed += 1
        except services.PickupServiceError:
            skipped += 1
    if changed:
        modeladmin.message_user(request, f"{changed} pickup {done_label}.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} pickup dilewati karena statusnya tidak sesuai.", messages.WARNING)


@admin.action(description="Batalkan pickup terpilih")
def cancel_pickups(modeladmin, request, queryset):
    _run_transition(
        modeladmin, request, queryset, Status.CANCELLED, PickupRequest.CANCELLABLE_STATUSES,
        "Dibatalkan oleh admin.", "dibatalkan",
    )


@admin.action(description="Kembalikan ke antrean (lepas kurir)")
def release_pickups(modeladmin, request, queryset):
    _run_transition(
        modeladmin, request, queryset, Status.PENDING, (Status.ASSIGNED,),
        "Dikembalikan ke antrean oleh admin.", "dikembalikan ke antrean",
    )


@admin.register(PickupRequest)
class PickupRequestAdmin(admin.ModelAdmin):
    list_display = (
        "short_id", "giver", "collector", "status", "scheduled_date", "time_slot",
        "total_estimated_weight", "completed_at", "verified_at",
    )
    list_filter = ("status", "scheduled_date", "time_slot", "incentive_allocation", "created_at")
    search_fields = (
        "=id", "pickup_address", "address_detail",
        "giver__username", "giver__email", "collector__username",
    )
    date_hierarchy = "created_at"
    list_select_related = ("giver", "collector")
    inlines = (PickupItemInline, PickupStatusHistoryInline)
    actions = (verify_pickups, cancel_pickups, release_pickups)
    # Status, people, and verification only change through the workflow,
    # so the status history stays complete. Address and schedule can be fixed.
    readonly_fields = (
        "giver", "collector", "status", "status_reason", "incentive_allocation",
        "created_at", "updated_at", "assigned_at", "completed_at", "cancelled_at",
        "verified_at", "verified_by",
    )
    fieldsets = (
        ("Status", {"fields": ("status", "status_reason", "giver", "collector", "incentive_allocation")}),
        ("Lokasi", {"fields": ("pickup_address", "address_detail", "latitude", "longitude", "contact_phone", "courier_note")}),
        ("Jadwal", {"fields": ("scheduled_date", "time_slot")}),
        ("Waktu & verifikasi", {"fields": (
            "created_at", "updated_at", "assigned_at", "completed_at", "cancelled_at", "verified_at", "verified_by",
        )}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_weight=Sum("items__estimated_weight"))

    @admin.display(description="ID", ordering="id")
    def short_id(self, obj):
        return f"#{str(obj.pk)[:8]}"

    @admin.display(description="Perkiraan berat", ordering="total_weight")
    def total_estimated_weight(self, obj):
        weight = obj.total_weight or 0
        return f"{weight:.2f} kg".replace(".", ",")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
