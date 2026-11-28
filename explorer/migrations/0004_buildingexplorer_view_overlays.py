from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('explorer', '0003_complexexplorer_ai_metadata_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='buildingexplorer',
            name='view_overlays',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
