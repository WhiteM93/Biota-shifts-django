from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0133_body_tool_modular_head_thread"),
    ]

    operations = [
        migrations.AddField(
            model_name="tapspec",
            name="thread_kind",
            field=models.CharField(
                choices=[
                    ("standard", "Стандарт"),
                    ("non_standard", "Не стандарт"),
                ],
                default="standard",
                max_length=16,
                verbose_name="Тип резьбы",
            ),
        ),
    ]
