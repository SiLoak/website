from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def landing_page(request):
    return render(request, "landing.html")


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
    return render(request, "profile.html", {"active_item": "profile"})


def legal_page(request, page):
    page_details = {
        "terms": ("Syarat & Ketentuan", "Ketentuan penggunaan layanan SiLoak."),
        "privacy": ("Kebijakan Privasi", "Informasi tentang pengelolaan data akun SiLoak."),
    }
    title, summary = page_details[page]
    return render(request, "legal.html", {"page_title": title, "summary": summary})
