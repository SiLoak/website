COLLECTOR_GROUP = "Collector"


def is_collector(user):
  return user.is_authenticated and user.groups.filter(name=COLLECTOR_GROUP).exists()


def is_giver(user):
  # Every signed-in user can hand over waste, except collector accounts.
  return user.is_authenticated and not is_collector(user)


def is_admin(user):
  return user.is_staff or user.is_superuser
