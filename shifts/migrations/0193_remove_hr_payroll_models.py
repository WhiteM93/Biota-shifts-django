# Generated manually for 152-FZ cleanup
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0192_site_stats"),
    ]

    operations = [
        migrations.DeleteModel(name="EmployeeDefectPayrollAdjustment"),
        migrations.DeleteModel(name="EmployeePayrollSettlement"),
        migrations.DeleteModel(name="EmployeePayrollMonthStatus"),
        migrations.DeleteModel(name="EmployeePayrollProfile"),
        migrations.DeleteModel(name="EmployeeDefectRecord"),
    ]
