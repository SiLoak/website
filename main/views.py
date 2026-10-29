from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse

from auth.forms import ProfileForm
from auth.models import UserProfile
from main.history import build_history_context
from pickup.models import PickupItem, PickupRequest
from pickup.permissions import is_collector, is_giver
from wallet.models import WalletTransaction
from waste.models import CollectionPoint, Submission


def landing_page(request):
    points = list(
        CollectionPoint.objects.filter(is_active=True)
        .exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .values("id", "name", "address", "latitude", "longitude", "operating_hours")
    )
    return render(request, "landing.html", {"map_points": points})


@login_required(login_url="auth_page")
def dashboard(request):
    if is_collector(request.user) and not is_giver(request.user):
        return redirect("pickup:show_collector_pickup_list")
    active_pickups = (
        PickupRequest.objects.filter(giver=request.user)
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
    history_activity = build_history_context(request.user)["activity"]
    return render(
        request,
        "dashboard.html",
        {
            "active_item": "dashboard",
            "active_pickup": active_pickup,
            "active_pickup_count": active_pickups.count(),
            "active_pickup_reference": str(active_pickup.pk)[:8] if active_pickup else "",
            "latest_pickup_event": active_pickup.status_history.order_by("-created_at").first() if active_pickup else None,
            "dashboard_activity": history_activity[:5],
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
