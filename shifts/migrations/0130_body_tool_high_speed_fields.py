from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0129_body_tool_chamfer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="hs_body_style",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("shell", "Насадная"),
                    ("end", "Концевая"),
                ],
                default="",
                max_length=12,
                verbose_name="Тип фрезы (насадная/концевая)",
            ),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="has_purpose",
            field=models.BooleanField(default=False, verbose_name="Назначение фрезы"),
        ),
    ]
