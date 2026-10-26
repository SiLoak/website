from django.shortcuts import render


def location_list(request):
    return render(request, "location/index.html", {"active_item": "location"})
