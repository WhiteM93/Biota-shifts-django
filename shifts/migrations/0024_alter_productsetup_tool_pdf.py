from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0023_productsetupphoto_setup"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productsetup",
            name="tool_pdf",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_tools/",
                validators=[django.core.validators.FileExtensionValidator(["pdf", "html", "htm"])],
                verbose_name="Инструмент (PDF/HTML)",
            ),
        ),
    ]
