from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0006_alter_regulationplan_eight_hour_shift_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="regulationplan",
            name="extra_end",
            field=models.TimeField(
                blank=True, help_text="Конец дополнительного ползунка.", null=True
            ),
        ),
        migrations.AddField(
            model_name="regulationplan",
            name="extra_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Название дополнительного ползунка сотрудника.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="regulationplan",
            name="extra_start",
            field=models.TimeField(
                blank=True, help_text="Начало дополнительного ползунка.", null=True
            ),
        ),
    ]
