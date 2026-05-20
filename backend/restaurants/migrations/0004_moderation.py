import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0003_shopimpression"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="ip_address",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="comment",
            name="user_agent",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="comment",
            name="is_hidden",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="comment",
            name="report_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="CommentReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("spam", "スパム / 広告"),
                            ("abuse", "誹謗中傷"),
                            ("false", "虚偽情報"),
                            ("privacy", "プライバシー侵害"),
                            ("other", "その他"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                ("detail", models.TextField(blank=True, default="")),
                ("reporter_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "comment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="restaurants.comment",
                    ),
                ),
                (
                    "reporter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "comment_reports",
                "ordering": ["-created_at"],
            },
        ),
    ]
