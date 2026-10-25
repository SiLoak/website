from django.shortcuts import render

def landing_page(request):
    return render(request, "landing.html")


def dashboard(request):
    return render(request, "index.html", {"active_item": "dashboard"})
