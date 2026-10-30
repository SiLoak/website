def user_roles(request):
    user = request.user
    if not user.is_authenticated:
        return {"user_is_giver": False, "user_is_collector": False}

    groups = set(user.groups.values_list("name", flat=True))
    return {
        "user_is_giver": "Giver" in groups,
        "user_is_collector": "Collector" in groups,
    }
