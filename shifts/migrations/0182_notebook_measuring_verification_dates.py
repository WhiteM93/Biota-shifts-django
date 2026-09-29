from django.db import migrations


NOTEBOOK_TITLE = "Измерительный: даты поверки"


def create_notebook_task(apps, schema_editor):
    SiteNotebookTask = apps.get_model("shifts", "SiteNotebookTask")
    if SiteNotebookTask.objects.filter(title=NOTEBOOK_TITLE).exists():
        return
    SiteNotebookTask.objects.create(
        author_username="system",
        title=NOTEBOOK_TITLE,
        body=(
            "Добавить на склад для измерительного инструмента поля: "
            "дата последней поверки и дата следующей поверки "
            "(пока отложено по решению при внедрении категории)."
        ),
        source_question="Пользователь: даты проверки пока не надо, но добавь задачу в блокнот.",
        page="inventory",
        panel="arrival",
        status="open",
    )


def remove_notebook_task(apps, schema_editor):
    SiteNotebookTask = apps.get_model("shifts", "SiteNotebookTask")
    SiteNotebookTask.objects.filter(title=NOTEBOOK_TITLE, author_username="system").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0181_measuring_thread_univ_fields"),
    ]

    operations = [
        migrations.RunPython(create_notebook_task, remove_notebook_task),
    ]
