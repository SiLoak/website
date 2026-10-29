from django.conf import settings
from django.db import migrations


def seed_user_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    manager = Group.objects.using(schema_editor.connection.alias)
    manager.get_or_create(name="Giver")
    manager.get_or_create(name="Collector")


class Migration(migrations.Migration):
    dependencies = [
        ("user_auth", "0003_userprofile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_user_groups, migrations.RunPython.noop),
    ]
