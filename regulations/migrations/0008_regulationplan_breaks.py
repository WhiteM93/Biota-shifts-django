from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0007_regulationplan_extra_slider_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="regulationplan",
            name="breaks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Список ползунков сотрудника: [{label,start,end,color_kind}].",
            ),
        ),
    ]
