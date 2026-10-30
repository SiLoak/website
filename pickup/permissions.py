GIVER_GROUP = "Giver"
COLLECTOR_GROUP = "Collector"


def is_giver(user):
  # New accounts join the Giver group automatically (auth/signals.py).
  return user.is_authenticated and user.groups.filter(name=GIVER_GROUP).exists()


def is_collector(user):
  return user.is_authenticated and user.groups.filter(name=COLLECTOR_GROUP).exists()


def is_admin(user):
  return user.is_staff or user.is_superuser
