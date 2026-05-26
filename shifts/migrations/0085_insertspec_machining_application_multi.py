from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0084_insertspec_machining_application"),
    ]

    operations = [
        migrations.AlterField(
            model_name="insertspec",
            name="machining_application",
            field=models.CharField(
                blank=True,
                default="",
                max_length=7,
                verbose_name="Вид обработки",
            ),
        ),
    ]
