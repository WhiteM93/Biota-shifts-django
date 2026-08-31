from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0122_visualcontainerphoto"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcontaineritem",
            name="rule_kind",
            field=models.CharField(
                choices=[("include", "Учитывать"), ("exclude", "Исключить")],
                default="include",
                help_text="Учитывать — что должно быть в ячейке; исключить — чего там быть не должно.",
                max_length=16,
                verbose_name="Режим правила",
            ),
        ),
    ]
