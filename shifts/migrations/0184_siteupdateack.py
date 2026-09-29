from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0183_measuring_check_mark_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteUpdateAck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_id", models.PositiveIntegerField(db_index=True, verbose_name="Id обновления")),
                ("username", models.CharField(db_index=True, max_length=120, verbose_name="Кто ознакомился")),
                ("acknowledged_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")),
            ],
            options={
                "verbose_name": "Ознакомление с обновлением",
                "verbose_name_plural": "Ознакомления с обновлениями",
                "ordering": ("acknowledged_at", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="siteupdateack",
            constraint=models.UniqueConstraint(
                fields=("update_id", "username"),
                name="site_update_ack_unique_user",
            ),
        ),
    ]
