from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0092_alter_product_card_workpiece_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="SectionActionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Когда")),
                (
                    "section",
                    models.CharField(
                        choices=[("graph", "График"), ("regulations", "Регламенты")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("event_type", models.CharField(db_index=True, max_length=32, verbose_name="Тип")),
                ("actor_username", models.CharField(max_length=120, verbose_name="Кто")),
                ("summary", models.CharField(max_length=500, verbose_name="Кратко")),
                ("details", models.JSONField(blank=True, default=dict, verbose_name="Детали")),
            ],
            options={
                "verbose_name": "Журнал графика/регламентов",
                "verbose_name_plural": "Журнал графика/регламентов",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
