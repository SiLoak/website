from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse

from auth.forms import ProfileForm
from auth.models import UserProfile
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
    return render(request, "dashboard.html", {"active_item": "dashboard"})


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
        "total_weight": total_weight,
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
