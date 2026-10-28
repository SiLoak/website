from django.contrib import admin, messages
from django.utils import timezone

from .models import CollectionPoint, Submission, SubmissionItem, WasteType


@admin.register(WasteType)
class WasteTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "rate_per_kg", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


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
    incomplete_count = 0

    for submission in pending_submissions:
        items = submission.items.all()
        if not items.exists() or items.filter(actual_weight__isnull=True).exists():
            incomplete_count += 1
            continue
        submission.status = Submission.Status.VERIFIED
        submission.verified_at = timezone.now()
        submission.verified_by = request.user
        submission.save(
            update_fields=["status", "verified_at", "verified_by", "updated_at"]
        )
        verified_count += 1

    if verified_count:
        modeladmin.message_user(
            request,
            f"{verified_count} pengajuan berhasil diverifikasi.",
            messages.SUCCESS,
        )
    if incomplete_count:
        modeladmin.message_user(
            request,
            f"{incomplete_count} pengajuan dilewati karena hasil timbang belum lengkap.",
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
