from django.shortcuts import render


def new_submission(request):
    return render(request, "waste/request.html", {"active_item": "waste"})


def dropoff_submission(request):
    return render(request, "waste/dropoff.html", {"active_item": "waste"})


def submission_detail(request, submission_id):
    return render(
        request,
        "waste/detail.html",
        {"active_item": "history", "submission_id": submission_id},
    )


def submission_history(request):
    return render(request, "history.html", {"active_item": "history"})
