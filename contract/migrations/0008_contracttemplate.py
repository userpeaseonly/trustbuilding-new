from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
        ('contract', '0007_contract_down_payment_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContractTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Template Name')),
                ('file', models.FileField(upload_to='contract_templates/', verbose_name='Template File (.docx)')),
                ('is_default', models.BooleanField(default=False, verbose_name='Is Default')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contract_templates', to='users.customuser')),
            ],
            options={
                'verbose_name': 'Contract Template',
                'verbose_name_plural': 'Contract Templates',
                'ordering': ['-is_default', '-created_at'],
            },
        ),
    ]
