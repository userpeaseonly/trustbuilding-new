from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_customuser_telegram_chat_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='face_image',
            field=models.ImageField(blank=True, null=True, upload_to='face_images/', verbose_name='Face Image'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='instagram_username',
            field=models.CharField(blank=True, max_length=255, verbose_name='Instagram Username'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='telegram_username',
            field=models.CharField(blank=True, max_length=255, verbose_name='Telegram Username'),
        ),
    ]
