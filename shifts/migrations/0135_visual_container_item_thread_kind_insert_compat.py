from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0134_tap_thread_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcontaineritem",
            name="thread_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Все"),
                    ("standard", "Стандарт"),
                    ("non_standard", "Не стандарт"),
                ],
                default="",
                help_text="Стандарт / не стандарт — для резьбового инструмента",
                max_length=16,
                verbose_name="Тип резьбы",
            ),
        ),
        migrations.AddField(
            model_name="visualcontaineritem",
            name="insert_compat",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Фильтр по совместимым пластинам корпусного инструмента",
                max_length=80,
                verbose_name="Подходящие пластины",
            ),
        ),
    ]
