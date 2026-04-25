from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0013_employeedefectrecord_department_name"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="employeedefectrecord",
            options={
                "ordering": ("-defect_date", "-id"),
                "verbose_name": "Запись учёта брака сотрудника",
                "verbose_name_plural": "Учёт брака сотрудников",
            },
        ),
    ]
