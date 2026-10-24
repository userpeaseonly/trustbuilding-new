from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import CustomUser


class TelegramReportSubscriber(models.Model):
    """
    Subscribers (Owners, Directors, CFOs, Sales Leads) who receive
    scheduled daily executive reports or real-time deal alerts via Telegram.
    """
    REPORT_LEVEL_CHOICES = [
        ('FULL_EXECUTIVE', _('Full Executive Cockpit (Sales, Inflows, Overdue, Balances)')),
        ('FINANCE_ONLY', _('Finance Only (Inflows, Overdue, Balances)')),
        ('SALES_ONLY', _('Sales Only (Today Sales, Overdue Debtors)')),
    ]

    company = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='telegram_report_subscribers',
        limit_choices_to={'is_company': True},
        verbose_name=_('Company')
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_subscriptions',
        verbose_name=_('User Account')
    )
    chat_id = models.BigIntegerField(_('Telegram Chat ID'), unique=True, db_index=True)
    telegram_username = models.CharField(_('Telegram Username'), max_length=255, blank=True)
    full_name = models.CharField(_('Recipient Name'), max_length=255)
    phone_number = models.CharField(_('Phone Number'), max_length=30, blank=True)
    
    report_level = models.CharField(
        _('Report Level'),
        max_length=30,
        choices=REPORT_LEVEL_CHOICES,
        default='FULL_EXECUTIVE'
    )
    
    # Granular schedule preferences
    receive_morning_report = models.BooleanField(_('09:00 AM Morning Briefing'), default=True)
    receive_evening_report = models.BooleanField(_('20:00 PM Evening Summary'), default=True)
    receive_sale_alerts = models.BooleanField(_('Instant Deal Alerts'), default=False)
    
    is_active = models.BooleanField(_('Active'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Telegram Report Subscriber')
        verbose_name_plural = _('Telegram Report Subscribers')
        ordering = ['company', '-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.get_report_level_display()}) - {self.company}"
