from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0168_work_position_operations_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="workcontractposition",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="Если задано — это отрыв (часть) от родительской позиции",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="splits",
                to="shifts.workcontractposition",
                verbose_name="Отрыв от",
            ),
        ),
    ]
