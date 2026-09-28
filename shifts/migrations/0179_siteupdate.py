from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0178_productsetup_needs_start"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteUpdate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")),
                ("author_username", models.CharField(blank=True, default="", max_length=120, verbose_name="Кто опубликовал")),
                ("title", models.CharField(max_length=200, verbose_name="Заголовок")),
                ("body", models.TextField(verbose_name="Что изменилось")),
            ],
            options={
                "verbose_name": "Обновление сайта",
                "verbose_name_plural": "Обновления сайта",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
