from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0065_backfill_plan_naladki_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="drawing_blank_size",
            field=models.CharField(
                blank=True,
                default="",
                max_length=180,
                verbose_name="Размер заготовки (изделие)",
                help_text="Общий размер заготовки по изделию; отображается на вкладке «Изделие».",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="drawing_blank_type",
            field=models.CharField(
                blank=True,
                default="",
                max_length=220,
                verbose_name="Тип заготовки (изделие)",
                help_text="Общее описание типа заготовки по изделию; отображается на вкладке «Изделие».",
            ),
        ),
    ]
