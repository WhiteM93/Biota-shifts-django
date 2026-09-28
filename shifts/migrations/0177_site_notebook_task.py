from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0176_body_tool_drill_cutter"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteNotebookTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")),
                ("author_username", models.CharField(db_index=True, max_length=120, verbose_name="Кто попросил")),
                ("title", models.CharField(max_length=200, verbose_name="Кратко")),
                ("body", models.TextField(verbose_name="Что сделать")),
                ("source_question", models.TextField(blank=True, default="", verbose_name="Исходный вопрос")),
                ("page", models.CharField(blank=True, default="", max_length=40, verbose_name="Страница")),
                ("panel", models.CharField(blank=True, default="", max_length=40, verbose_name="Вкладка")),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Открыта"), ("done", "Выполнено")],
                        db_index=True,
                        default="open",
                        max_length=12,
                        verbose_name="Статус",
                    ),
                ),
                ("done_at", models.DateTimeField(blank=True, null=True, verbose_name="Когда закрыто")),
                ("done_by", models.CharField(blank=True, default="", max_length=120, verbose_name="Кто закрыл")),
            ],
            options={
                "verbose_name": "Задача блокнота сайта",
                "verbose_name_plural": "Блокнот доработок сайта",
                "ordering": ("status", "-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["status", "-created_at"], name="site_nb_status_created"),
                ],
            },
        ),
    ]
