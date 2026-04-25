from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0021_productsetup_structured_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="tool_pdf",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_tools/",
                validators=[django.core.validators.FileExtensionValidator(["pdf"])],
                verbose_name="Инструмент (PDF)",
            ),
        ),
    ]
