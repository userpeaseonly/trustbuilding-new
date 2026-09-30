from django.db import migrations

def populate_contract_id(apps, schema_editor):
    Contract = apps.get_model('contract', 'Contract')
    companies = Contract.objects.values_list('company', flat=True).distinct()
    for company_id in companies:
        contracts = Contract.objects.filter(company_id=company_id).order_by('created_at', 'id')
        current_id = 1
        for contract in contracts:
            contract.contract_id = current_id
            contract.save(update_fields=['contract_id'])
            current_id += 1

def reverse_populate(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('contract', '0012_contract_contract_id'),
    ]
    operations = [
        migrations.RunPython(populate_contract_id, reverse_populate),
    ]
