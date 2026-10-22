from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = _('Finance & Cash Flow')

    def ready(self):
        try:
            import finance.signals  # noqa
        except ImportError:
            pass
