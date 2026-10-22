from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from users.models import CustomUser


class Wallet(models.Model):
    """
    Physical or digital money storage (Cash desk, Bank account, Card, etc.)
    Strictly scoped to a company.
    """
    WALLET_TYPE_CHOICES = [
        ('CASH', _('Cash Desk (Наличные)')),
        ('BANK', _('Bank Account (Расчетный счет)')),
        ('CARD', _('Corporate Card (Корпоративная карта)')),
        ('OTHER', _('Other (Другое)')),
    ]

    CURRENCY_CHOICES = [
        ('UZS', _("O'zbek so'mi (UZS)")),
        ('USD', _('US Dollar (USD)')),
    ]

    company = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='company_wallets',
        limit_choices_to={'is_company': True},
        verbose_name=_('Company')
    )
    name = models.CharField(_('Account / Cash Desk Name'), max_length=255)
    wallet_type = models.CharField(_('Account Type'), max_length=20, choices=WALLET_TYPE_CHOICES, default='CASH')
    currency = models.CharField(_('Currency'), max_length=10, choices=CURRENCY_CHOICES, default='UZS')
    initial_balance = models.DecimalField(_('Initial Balance'), max_digits=18, decimal_places=2, default=0.00)
    
    bank_name = models.CharField(_('Bank Name'), max_length=255, blank=True)
    account_number = models.CharField(_('Account Number / Card'), max_length=50, blank=True)
    mfo = models.CharField(_('MFO / Routing'), max_length=20, blank=True)
    
    is_active = models.BooleanField(_('Active'), default=True)
    is_default = models.BooleanField(_('Default for Cash Receipts'), default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Cash Desk / Account')
        verbose_name_plural = _('Cash Desks & Accounts')
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_currency_display()})"

    @property
    def current_balance(self):
        """
        Dynamically calculates the exact mathematical balance:
        Initial Balance + Inflows (INCOME + inbound TRANSFERS) - Outflows (EXPENSE + outbound TRANSFERS)
        """
        incomes = self.transactions.filter(transaction_type='INCOME').aggregate(total=Sum('amount'))['total'] or 0
        inbound_transfers = self.inbound_transfers.filter(transaction_type='TRANSFER').aggregate(total=Sum('amount'))['total'] or 0
        
        expenses = self.transactions.filter(transaction_type='EXPENSE').aggregate(total=Sum('amount'))['total'] or 0
        outbound_transfers = self.transactions.filter(transaction_type='TRANSFER').aggregate(total=Sum('amount'))['total'] or 0
        
        return self.initial_balance + incomes + inbound_transfers - expenses - outbound_transfers


class ExpenseCategory(models.Model):
    """
    Categorization for financial outflows and manual inflows.
    """
    CATEGORY_TYPE_CHOICES = [
        ('EXPENSE', _('Expense (Расход)')),
        ('INCOME', _('Income (Приход)')),
    ]

    company = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='company_expense_categories',
        limit_choices_to={'is_company': True},
        verbose_name=_('Company')
    )
    name = models.CharField(_('Category Name'), max_length=255)
    category_type = models.CharField(_('Category Type'), max_length=20, choices=CATEGORY_TYPE_CHOICES, default='EXPENSE')
    is_system = models.BooleanField(_('System Category'), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Expense Category')
        verbose_name_plural = _('Expense Categories')
        unique_together = ('company', 'name', 'category_type')
        ordering = ['name']

    def __str__(self):
        return self.name


class FinancialTransaction(models.Model):
    """
    Core Double-Entry / Ledger Record for all cash flow operations.
    """
    TRANSACTION_TYPE_CHOICES = [
        ('INCOME', _('Income (Приход)')),
        ('EXPENSE', _('Expense (Расход)')),
        ('TRANSFER', _('Transfer (Перевод / Инкассация)')),
    ]

    company = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='company_financial_transactions',
        limit_choices_to={'is_company': True},
        verbose_name=_('Company')
    )
    transaction_type = models.CharField(_('Transaction Type'), max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    
    # Primary / Source Wallet
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name=_('Cash Desk / Account')
    )
    
    # Destination Wallet for Transfers
    target_wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inbound_transfers',
        verbose_name=_('Destination Account (for Transfer)')
    )
    
    amount = models.DecimalField(_('Amount'), max_digits=18, decimal_places=2)
    date = models.DateField(_('Date'), default=timezone.now)
    
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        verbose_name=_('Category')
    )
    
    # Optional Project / Building Cost Allocation
    building = models.ForeignKey(
        'building.Building',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_transactions',
        verbose_name=_('Building / Object')
    )
    
    # Optional Contract & Receipt Links
    contract = models.ForeignKey(
        'contract.Contract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_transactions',
        verbose_name=_('Contract')
    )
    payment_log = models.OneToOneField(
        'contract.PaymentLog',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='financial_transaction',
        verbose_name=_('Payment Receipt')
    )
    
    description = models.TextField(_('Description / Note'), blank=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_financial_transactions',
        verbose_name=_('Recorded By')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Financial Transaction')
        verbose_name_plural = _('Financial Transactions')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} UZS ({self.date})"
