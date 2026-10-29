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
    readonly_fields = ("waste_type", "unit_rate_snapshot")

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
        "total_estimated_weight", "created_at",
    )
    list_filter = ("status", "scheduled_date", "time_slot", "incentive_allocation", "created_at")
    search_fields = ("pickup_address", "address_detail", "giver__username", "giver__email", "collector__username")
    date_hierarchy = "created_at"
    list_select_related = ("giver", "collector")
    inlines = (PickupItemInline, PickupStatusHistoryInline)
    actions = (cancel_pickups, release_pickups)
    # Status and people only change through the workflow, so history stays complete.
    readonly_fields = (
        "giver", "collector", "status", "status_reason", "incentive_allocation",
        "created_at", "updated_at", "assigned_at", "completed_at", "cancelled_at",
    )
    fieldsets = (
        ("Status", {"fields": ("status", "status_reason", "giver", "collector", "incentive_allocation")}),
        ("Lokasi", {"fields": ("pickup_address", "address_detail", "latitude", "longitude", "contact_phone", "courier_note")}),
        ("Jadwal", {"fields": ("scheduled_date", "time_slot")}),
        ("Waktu", {"fields": ("created_at", "updated_at", "assigned_at", "completed_at", "cancelled_at")}),
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
