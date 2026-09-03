from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0132_body_tool_ball_shank_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="mount_thread",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("M6", "М6"),
                    ("M8", "М8"),
                    ("M10", "М10"),
                    ("M12", "М12"),
                    ("M16", "М16"),
                    ("M20", "М20"),
                ],
                default="",
                max_length=8,
                verbose_name="Резьба крепления",
            ),
        ),
    ]
