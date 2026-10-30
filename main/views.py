from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from auth.forms import ProfileForm
from auth.models import UserProfile
from location import services as location_services
from main.history import build_history_context
from pickup.models import PickupItem, PickupRequest
from pickup.permissions import is_collector, is_giver
from wallet.models import Wallet, WalletTransaction
from waste.models import CollectionPoint, Submission, SubmissionItem


def landing_page(request):
    # Points come from the location module so the landing map matches /location/.
    points = location_services.points_payload()
    featured = sorted(points, key=lambda point: (point["is_open"] is None, not point["address"]))[:4]
    return render(request, "landing.html", {
        "map_points": points,
        "featured_points": featured,
        "point_count": len(points),
    })


@login_required(login_url="auth_page")
def dashboard(request):
    if is_collector(request.user) and not is_giver(request.user):
        return redirect("pickup:show_collector_pickup_list")

    user = request.user
    today = timezone.localdate()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    active_pickups = (
        PickupRequest.objects.filter(giver=user)
        .exclude(
            status__in=(
                PickupRequest.Status.COMPLETED,
                PickupRequest.Status.CANCELLED,
                PickupRequest.Status.FAILED,
            )
        )
        .select_related("collector")
    )
    active_pickup = active_pickups.first()
    history_context = build_history_context(user)
    history_activity = history_context["activity"]

    submissions = Submission.objects.filter(user=user)
    pickups = PickupRequest.objects.filter(giver=user)
    month_submissions = submissions.filter(
        created_at__date__gte=month_start,
        created_at__date__lte=today,
    ).exclude(status=Submission.Status.CANCELED)
    month_pickups = pickups.filter(
        created_at__date__gte=month_start,
        created_at__date__lte=today,
    ).exclude(
        status__in=(PickupRequest.Status.CANCELLED, PickupRequest.Status.FAILED)
    )

    month_completed_count = submissions.filter(
        status=Submission.Status.VERIFIED,
        verified_at__date__gte=month_start,
        verified_at__date__lte=today,
    ).count() + pickups.filter(
        status=PickupRequest.Status.COMPLETED,
        completed_at__date__gte=month_start,
        completed_at__date__lte=today,
    ).count()
    total_completed_count = submissions.filter(
        status=Submission.Status.VERIFIED
    ).count() + pickups.filter(status=PickupRequest.Status.COMPLETED).count()

    weekly_submission_weight = SubmissionItem.objects.filter(
        submission__user=user,
        submission__status=Submission.Status.VERIFIED,
        submission__verified_at__date__gte=week_start,
        submission__verified_at__date__lte=today,
    ).aggregate(total=Sum("actual_weight"))["total"] or 0
    weekly_pickup_weight = PickupItem.objects.filter(
        pickup_request__giver=user,
        pickup_request__status=PickupRequest.Status.COMPLETED,
        pickup_request__completed_at__date__gte=week_start,
        pickup_request__completed_at__date__lte=today,
    ).aggregate(total=Sum("actual_weight"))["total"] or 0

    wallet = Wallet.objects.filter(user=user).first()
    wallet_balance = wallet.balance if wallet else 0
    latest_activity_location = (
        history_activity[0]["location"] if history_activity else ""
    )
    active_collection_point_count = CollectionPoint.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
    ).count()

    return render(
        request,
        "dashboard.html",
        {
            "active_item": "dashboard",
            "dashboard_name": user.first_name.strip() or user.get_username(),
            "latest_activity_location": latest_activity_location,
            "active_pickup": active_pickup,
            "active_pickup_count": active_pickups.count(),
            "active_pickup_reference": str(active_pickup.pk)[:8] if active_pickup else "",
            "latest_pickup_event": active_pickup.status_history.order_by("-created_at").first() if active_pickup else None,
            "dashboard_activity": history_activity[:5],
            "dashboard_activity_count": len(history_activity[:5]),
            "wallet_balance": wallet_balance,
            "wallet_balance_display": f"{wallet_balance:,.0f}".replace(",", "."),
            "total_actual_weight": history_context["total_actual_weight"],
            "weekly_actual_weight": weekly_submission_weight + weekly_pickup_weight,
            "month_activity_count": month_submissions.count() + month_pickups.count(),
            "month_completed_count": month_completed_count,
            "current_month": today,
            "total_completed_count": total_completed_count,
            "active_collection_point_count": active_collection_point_count,
        },
    )


def wallet(request):
    return render(request, "wallet/wallet.html", {"active_item": "wallet"})

def withdraw(request):
    return render(request, "wallet/withdraw.html", {"active_item": "wallet"})


@login_required(login_url="auth_page")
def history(request):
    return redirect("waste:submissions")


@login_required(login_url="auth_page")
def profile(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    form = ProfileForm(request.POST or None, user=user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Perubahan profil berhasil disimpan.")
            return redirect("profile")
        messages.error(request, "Periksa kembali nama dan nomor HP yang kamu masukkan.")

    submissions = Submission.objects.filter(user=user)
    total_weight = submissions.filter(status=Submission.Status.VERIFIED).aggregate(
        total=Sum("items__actual_weight")
    )["total"] or 0
    pickups = PickupRequest.objects.filter(giver=user)
    pickup_weight = PickupItem.objects.filter(
        pickup_request__giver=user,
        pickup_request__status=PickupRequest.Status.COMPLETED,
    ).aggregate(total=Sum("actual_weight"))["total"] or 0
    activity = []
    for submission in submissions[:5]:
        activity.append({
            "date": submission.created_at,
            "title": f"Setoran #{submission.pk}",
            "status": submission.get_status_display(),
            "url": reverse("waste:detail", args=[submission.pk]),
            "kind": "submission",
            "amount": None,
        })
    for pickup in pickups[:5]:
        status = pickup.get_status_display()
        if pickup.status == PickupRequest.Status.COMPLETED and pickup.verified_at is None:
            status = "Selesai · menunggu verifikasi insentif"
        activity.append({
            "date": pickup.created_at,
            "title": f"Pickup #{str(pickup.pk)[:8]}",
            "status": status,
            "url": reverse("pickup:show_pickup_detail", args=[pickup.pk]),
            "kind": "pickup",
            "amount": None,
        })
    for transaction in WalletTransaction.objects.filter(wallet__user=user)[:5]:
        activity.append({
            "date": transaction.created_at,
            "title": transaction.description,
            "status": transaction.get_status_display(),
            "url": reverse("wallet:index"),
            "kind": "wallet",
            "amount": transaction.amount,
        })
    activity.sort(key=lambda item: item["date"], reverse=True)
    try:
        google_connected = user.google_identity is not None
    except ObjectDoesNotExist:
        google_connected = False
    return render(request, "profile.html", {
        "active_item": "profile",
        "form": form,
        "profile": profile,
        "submission_count": submissions.count(),
        "pickup_count": pickups.count(),
        "total_weight": total_weight + pickup_weight,
        "activity": activity[:5],
        "google_connected": google_connected,
    })


def legal_page(request, page):
    page_details = {
        "terms": ("Syarat & Ketentuan", "Ketentuan penggunaan layanan SiLoak."),
        "privacy": ("Kebijakan Privasi", "Informasi tentang pengelolaan data akun SiLoak."),
    }
    title, summary = page_details[page]
    return render(request, "legal.html", {"page_title": title, "summary": summary})
