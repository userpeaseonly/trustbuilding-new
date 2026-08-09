from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_customuser_face_image_social_usernames'),
    ]

    operations = [
        migrations.AddField(
            model_name='branch',
            name='latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Branch GPS latitude for mobile map/location display.',
                max_digits=9,
                null=True,
                verbose_name='Latitude',
            ),
        ),
        migrations.AddField(
            model_name='branch',
            name='longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Branch GPS longitude for mobile map/location display.',
                max_digits=9,
                null=True,
                verbose_name='Longitude',
            ),
        ),
    ]
