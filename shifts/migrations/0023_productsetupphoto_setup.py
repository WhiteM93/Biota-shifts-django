from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0022_productsetup_tool_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetupphoto",
            name="setup",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="photos",
                to="shifts.productsetup",
                verbose_name="Установка",
            ),
        ),
    ]
