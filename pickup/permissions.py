def is_giver(user):
  return user.groups.filter(name='Giver').exists()


def is_collector(user):
  return user.groups.filter(name='Collector').exists()


def is_admin(user):
  return user.is_staff or user.is_superuser