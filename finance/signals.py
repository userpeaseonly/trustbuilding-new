from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from contract.models import PaymentLog
from .models import Wallet, FinancialTransaction, ExpenseCategory


@receiver(post_save, sender=PaymentLog)
def sync_payment_log_to_finance(sender, instance, created, **kwargs):
    """
    Automatically reflects contract payment receipts into the Finance cash flow ledger.
    """
    if not instance.contract or not instance.contract.company:
        return
        
    company = instance.contract.company
    
    # Map payment type to corresponding wallet type
    wallet_type_map = {
        'CASH': 'CASH',
        'BANK': 'BANK',
        'CARD': 'CARD',
        'MATERIAL': 'CASH',
    }
    target_wallet_type = wallet_type_map.get(instance.payment_type, 'CASH')
    
    # Find existing wallet matching type or default
    wallet = Wallet.objects.filter(company=company, wallet_type=target_wallet_type, is_active=True).first()
    if not wallet:
        # Fallback to any active wallet, or create default cash desk
        wallet = Wallet.objects.filter(company=company, is_active=True).first()
        if not wallet:
            wallet = Wallet.objects.create(
                company=company,
                name="Главная касса",
                wallet_type='CASH',
                currency='UZS',
                is_default=True
            )
            
    # Auto-get or create system Income Category
    category, _ = ExpenseCategory.objects.get_or_create(
        company=company,
        name="Оплата по договорам (Поступления от клиентов)",
        category_type='INCOME',
        defaults={'is_system': True}
    )
    
    building = None
    if hasattr(instance.contract, 'apartment') and instance.contract.apartment:
        building = instance.contract.apartment.building
        
    client_name = instance.contract.customer.full_name or str(instance.contract.customer.phone_number)
    desc = f"Оплата по договору №{instance.contract.contract_id} ({client_name})"
    if getattr(instance, 'transaction_id', ''):
        desc += f" [ID: {instance.transaction_id}]"
        
    payment_date = instance.date_paid.date() if hasattr(instance.date_paid, 'date') else instance.date_paid

    FinancialTransaction.objects.update_or_create(
        payment_log=instance,
        defaults={
            'company': company,
            'transaction_type': 'INCOME',
            'wallet': wallet,
            'amount': instance.amount,
            'date': payment_date,
            'category': category,
            'building': building,
            'contract': instance.contract,
            'description': desc,
        }
    )
