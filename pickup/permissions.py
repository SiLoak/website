from rest_framework.permissions import BasePermission

def is_admin(user):
  return user.is_staff or user.is_superuser

def is_giver(user):
  return user.groups.filter(name='Giver').exists()

def is_collector(user):
  return user.groups.filter(name='Collector').exists()

class IsGiver(BasePermission):
  def has_permission(self, request, view):
    return is_giver(request.user)

class IsCollector(BasePermission):
  def has_permission(self, request, view):
    return is_collector(request.user)
