from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_customuser_email_delete_userroleassignment'),
    ]

    operations = [
        migrations.AddField(
            model_name='branch',
            name='short_name',
            field=models.CharField(
                blank=True,
                help_text="Abbreviated branch code used in group names, e.g. 'CHI' for Chilonzor.",
                max_length=10,
                verbose_name='Short Name',
            ),
        ),
    ]
