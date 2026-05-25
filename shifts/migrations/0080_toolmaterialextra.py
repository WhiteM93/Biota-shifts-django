from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0079_userhomelowstockprefs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ToolMaterialExtra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(max_length=80, unique=True, verbose_name="Материал")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Материал инструмента (доп.)",
                "verbose_name_plural": "Материалы инструмента (доп.)",
                "ordering": ("value",),
            },
        ),
    ]
