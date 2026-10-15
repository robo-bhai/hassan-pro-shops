import os
from django.core.cache import cache
from app.models import SystemSetting
from app.module_catalog import MODULE_CATALOG

want = os.environ.get('MODULES', 'all')
keys = [m['key'] for m in MODULE_CATALOG]
chosen = keys if want == 'all' else [k.strip() for k in want.split(',') if k.strip() in keys]
for k in chosen:
    SystemSetting.set_value('mode_shop_%s' % k, True)
    SystemSetting.set_value('mode_factory_%s' % k, True)
    SystemSetting.set_value('show_%s_module' % k, True)
cache.delete('module_visibility')
print('ON kiye gaye:', chosen)
