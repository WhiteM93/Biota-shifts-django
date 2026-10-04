"""Подпись кода мебели: «Код мебели», подсказка про 3 символа в адресе."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0190_shelf_numbers_top_down"),
    ]

    operations = [
        migrations.AlterField(
            model_name="visualcabinet",
            name="code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="До 3 символов (буквы/цифры) в адресе: A1-01-02, 12-03-01…",
                max_length=8,
                verbose_name="Код мебели",
            ),
        ),
    ]
