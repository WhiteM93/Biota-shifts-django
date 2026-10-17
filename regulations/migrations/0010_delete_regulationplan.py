from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0009_remove_plan_date"),
    ]

    operations = [
        migrations.DeleteModel(name="RegulationPlan"),
    ]
