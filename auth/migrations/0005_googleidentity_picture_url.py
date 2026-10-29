from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("user_auth", "0004_seed_user_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="googleidentity",
            name="picture_url",
            field=models.URLField(blank=True),
        ),
    ]
