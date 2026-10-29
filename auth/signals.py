from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=get_user_model())
def add_new_user_to_giver_group(sender, instance, created, **kwargs):
    if not created:
        return

    giver_group, _ = Group.objects.get_or_create(name="Giver")
    instance.groups.add(giver_group)
