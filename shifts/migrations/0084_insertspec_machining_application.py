from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0083_insert_spec_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="insertspec",
            name="machining_application",
            field=models.CharField(
                choices=[
                    ("1", "Чистовая"),
                    ("2", "Получистовая"),
                    ("3", "Черновая"),
                ],
                default="3",
                max_length=1,
                verbose_name="Вид обработки",
            ),
        ),
    ]
