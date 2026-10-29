from django.contrib import admin, messages

from pickup import services
from pickup.models import PickupItem, PickupRequest, PickupStatusHistory


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
