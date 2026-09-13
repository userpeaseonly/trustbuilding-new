from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('contract', '0008_contracttemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='contracttemplate',
            name='content_html',
            field=models.TextField(blank=True, verbose_name='HTML Content'),
        ),
    ]
