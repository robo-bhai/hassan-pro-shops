from django.core.cache import cache
from django.template.loader import get_template
from app.models import SystemSetting
from app.module_catalog import MODULE_CATALOG
from app.context_processors import module_visibility, unit_enabled

cache.delete('module_visibility')
vis = module_visibility()
GATED = {'sales', 'purchase', 'installment', 'inventory', 'production', 'hr', 'reports', 'whatsapp', 'backup'}

print('sidebar file used :', get_template('components/sidebar.html').origin.name)
print('business_mode     :', vis['_mode'])
print()
print('%-13s %-6s %-8s %-8s %s' % ('module', 'Shop', 'Factory', 'RESULT', 'sidebar'))
for m in MODULE_CATALOG:
    k = m['key']
    s = 'ON' if unit_enabled(k, 'shop') else 'off'
    f = 'ON' if unit_enabled(k, 'factory') else 'off'
    res = 'SHOWN' if vis[k] else 'HIDDEN'
    note = 'switch works' if k in GATED else 'no switch (always visible)'
    print('%-13s %-6s %-8s %-8s %s' % (k, s, f, res, note))
