from django.shortcuts import render


def request_pickup(request):
    return render(request, "waste/request.html", {"active_item": "waste"})


def pickup_detail(request, pickup_id):
    return render(
        request,
        "waste/detail.html",
        {"active_item": "history", "submission_id": pickup_id},
    )
