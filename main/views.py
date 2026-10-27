from django.shortcuts import redirect, render


def landing_page(request):
    return render(request, "landing.html")


def dashboard(request):
    return render(request, "dashboard.html", {"active_item": "dashboard"})


def wallet(request):
    return render(request, "wallet.html", {"active_item": "wallet"})


def history(request):
    return redirect("waste:submissions")


def profile(request):
    return render(request, "profile.html", {"active_item": "profile"})


def legal_page(request, page):
    page_details = {
        "terms": ("Syarat & Ketentuan", "Ketentuan penggunaan layanan SiLoak."),
        "privacy": ("Kebijakan Privasi", "Informasi tentang pengelolaan data akun SiLoak."),
    }
    title, summary = page_details[page]
    return render(request, "legal.html", {"page_title": title, "summary": summary})
