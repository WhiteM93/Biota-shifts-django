from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0184_siteupdateack"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="created_by",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=200,
                verbose_name="Автор наладки",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="editors",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Логины тех, кто правил карточку после автора.",
                verbose_name="Редакторы",
            ),
        ),
    ]
