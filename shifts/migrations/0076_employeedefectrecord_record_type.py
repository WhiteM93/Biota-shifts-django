from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0075_productsetup_binding_extra_blocks"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeedefectrecord",
            name="record_type",
            field=models.CharField(
                choices=[("scold", "Поругать"), ("praise", "Похвалить")],
                default="scold",
                max_length=10,
                verbose_name="Тип записи",
            ),
        ),
    ]
