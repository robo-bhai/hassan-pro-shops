"""Agri Edition switch.

  python manage.py agri_edition status
  python manage.py agri_edition on     # simple menu: only what a fertilizer / agri-medicine shop needs
  python manage.py agri_edition off    # restore the previous module settings

Nothing is deleted: only the module visibility switches (SystemSetting) are changed, and the
previous values are saved so `off` puts everything back.
"""
import json
import os

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

from app.models import SystemSetting

HIDE = ['production', 'store_issue', 'installment', 'supply_chain', 'services', 'operations',
        'loans', 'budgets', 'shareholders', 'dividends', 'hr', 'bi', 'ai', 'audit',
        'documents', 'testing']
SHOW = ['inventory', 'purchase', 'sales', 'accounts', 'cash', 'whatsapp', 'reports', 'backup', 'agri']
STATE_KEY = 'agri_edition_on'          # marker row in SystemSetting
STATE_FILE = os.path.join(str(settings.BASE_DIR), 'agri_edition_prev_state.json')   # previous values


def _set(key, value):
    SystemSetting.objects.update_or_create(setting_key=key, defaults={'setting_value': value})


class Command(BaseCommand):
    help = 'Agri Edition: simple menu on / off / status'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['on', 'off', 'status'])

    def handle(self, *args, **opts):
        action = opts['action']
        saved = SystemSetting.objects.filter(setting_key=STATE_KEY).first()
        if action == 'status':
            self.stdout.write('Agri Edition simple menu: %s' % ('ON' if saved else 'OFF'))
            self.stdout.write('business_mode = %s' % SystemSetting.get_value('business_mode', 'both'))
            return

        if action == 'on':
            if saved:
                self.stdout.write(self.style.WARNING('Already ON (previous settings are already saved in agri_edition_prev_state.json).'))
                return
            keys = ['business_mode'] + ['mode_shop_%s' % k for k in HIDE + SHOW]
            prev = {}
            for k in keys:
                row = SystemSetting.objects.filter(setting_key=k).first()
                prev[k] = row.setting_value if row else None
            with open(STATE_FILE, 'w') as fh:
                json.dump(prev, fh)
            _set(STATE_KEY, 'true')
            _set('business_mode', 'shop')
            for k in HIDE:
                _set('mode_shop_%s' % k, 'false')
            for k in SHOW:
                _set('mode_shop_%s' % k, 'true')
            cache.delete('module_visibility')
            self.stdout.write(self.style.SUCCESS('Agri Edition ON. Hidden modules: ' + ', '.join(HIDE)))
            self.stdout.write('Reload the browser (menu refreshes within a minute). Undo: agri_edition off')
            return

        # off
        if not saved:
            self.stdout.write(self.style.WARNING('Agri Edition simple menu is not ON.'))
            return
        try:
            with open(STATE_FILE) as fh:
                prev = json.load(fh)
        except (OSError, ValueError):
            prev = {}
        for k, v in prev.items():
            if v is None:
                SystemSetting.objects.filter(setting_key=k).delete()
            else:
                _set(k, v)
        saved.delete()
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass
        cache.delete('module_visibility')
        self.stdout.write(self.style.SUCCESS('Agri Edition OFF. Previous module settings restored.'))
