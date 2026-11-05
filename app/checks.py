# app/checks.py   (import it in AppConfig.ready())
from django.conf import settings
from django.core.checks import Error, register


@register()
def mysql_only(app_configs, **kwargs):
    engine = settings.DATABASES["default"]["ENGINE"]
    if "mysql" not in engine:
        return [Error(f"Only MySQL is allowed, got {engine}", id="erp.E001")]
    return []
