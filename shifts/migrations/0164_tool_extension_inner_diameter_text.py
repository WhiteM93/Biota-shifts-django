from decimal import Decimal

from django.db import migrations, models


def copy_inner_diameter_mm_to_text(apps, schema_editor):
    Spec = apps.get_model("shifts", "ToolExtensionSpec")
    for row in Spec.objects.exclude(inner_diameter_mm__isnull=True).iterator():
        val = row.inner_diameter_mm
        if val is None:
            text = ""
        else:
            try:
                d = Decimal(str(val))
                s = format(d, "f")
                if "." in s:
                    s = s.rstrip("0").rstrip(".")
                text = s or "0"
            except Exception:
                text = str(val)
        Spec.objects.filter(pk=row.pk).update(inner_diameter=(text or "")[:40])


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0163_tool_extension_inner_diameter"),
    ]

    operations = [
        migrations.AddField(
            model_name="toolextensionspec",
            name="inner_diameter",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Для термо и боковой фиксации: мм, дюймы (1/2) или G1/8",
                max_length=40,
                verbose_name="Внутренний диаметр Dвн",
            ),
        ),
        migrations.RunPython(copy_inner_diameter_mm_to_text, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="toolextensionspec",
            name="inner_diameter_mm",
        ),
    ]
