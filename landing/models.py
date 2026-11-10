from django.db import models
from django.utils.translation import gettext_lazy as _


class LeadRequest(models.Model):
    STATUS_NEW = 'NEW'
    STATUS_CONTACTED = 'CONTACTED'
    STATUS_DEMO = 'DEMO_SCHEDULED'
    STATUS_CLOSED = 'CLOSED'

    STATUS_CHOICES = [
        (STATUS_NEW, _('Yangi / New')),
        (STATUS_CONTACTED, _('Bogʻlanildi / Contacted')),
        (STATUS_DEMO, _('Demo belgilandi / Demo Scheduled')),
        (STATUS_CLOSED, _('Yakunlandi / Closed')),
    ]

    APARTMENTS_CHOICES = [
        ('1-50', '1 - 50 xonadon'),
        ('50-200', '50 - 200 xonadon'),
        ('200+', '200+ xonadon'),
        ('other', 'Boshqa / Rejalashtirilmoqda'),
    ]

    full_name = models.CharField(_('Ism-familiya'), max_length=150)
    phone_number = models.CharField(_('Telefon raqam'), max_length=30)
    company_name = models.CharField(_('Kompaniya nomi'), max_length=200, blank=True)
    apartments_count = models.CharField(_('Xonadonlar soni'), max_length=50, choices=APARTMENTS_CHOICES, blank=True, default='50-200')
    preferred_language = models.CharField(_('Afzal koʻrilgan til'), max_length=5, default='uz', choices=[('uz', 'Oʻzbekcha'), ('ru', 'Русский')])
    notes = models.TextField(_('Izoh / Qoʻshimcha maʼlumot'), blank=True)
    
    status = models.CharField(_('Holat'), max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    telegram_notified = models.BooleanField(_('Telegramga yuborildi'), default=False)
    ip_address = models.GenericIPAddressField(_('IP manzil'), null=True, blank=True)
    
    created_at = models.DateTimeField(_('Yaratilgan vaqt'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Yangilangan vaqt'), auto_now=True)

    class Meta:
        verbose_name = _('Demo soʻrovi (Lead)')
        verbose_name_plural = _('Demo soʻrovlari (Leads)')
        ordering = ['-created_at']

    def __str__(self):
        comp = f" ({self.company_name})" if self.company_name else ""
        return f"{self.full_name}{comp} - {self.phone_number}"
