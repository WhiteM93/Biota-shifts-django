from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0121_alter_employeedefectpayrolladjustment_adjust_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="VisualContainerPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "image",
                    models.FileField(
                        upload_to="visual_warehouse/container_photos/",
                        validators=[
                            django.core.validators.FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])
                        ],
                        verbose_name="Фото",
                    ),
                ),
                ("photo_date", models.DateField(verbose_name="Дата фото")),
                ("caption", models.CharField(blank=True, default="", max_length=200, verbose_name="Подпись")),
                ("uploaded_by", models.CharField(blank=True, default="", max_length=120, verbose_name="Загрузил")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "container",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="shifts.visualcontainer",
                        verbose_name="Контейнер",
                    ),
                ),
            ],
            options={
                "verbose_name": "Фото содержимого контейнера",
                "verbose_name_plural": "Фото содержимого контейнеров",
                "ordering": ("-photo_date", "-id"),
            },
        ),
    ]
