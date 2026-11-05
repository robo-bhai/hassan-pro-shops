"""Lite Edition switch (simple Urdu-first mode for small shops).

  python manage.py lite_edition status
  python manage.py lite_edition on                       # everyday modules only, Urdu default
  python manage.py lite_edition on --also installment    # keep extra modules (installment hr loans services)
  python manage.py lite_edition on --lang en             # Lite menu but English default
  python manage.py lite_edition off                      # restore the previous module settings

The same switch is on the Module Settings page (Settings > Modules > Lite Edition).
Nothing is deleted: only module visibility (SystemSetting) changes. The previous values are saved
in lite_edition_prev_state.json so `off` puts everything back. If that file is missing (for example
after a Docker rebuild) `off` removes the Lite rows, which returns every module to its default (ON).
"""
from django.core.management.base import BaseCommand, CommandError

from app.lite_edition import (LITE_DEFAULT_LANG, LITE_LANG_KEY, LITE_MARKER, LITE_OPTIONAL,
                              disable_lite, enable_lite)
from app.models import SystemSetting


class Command(BaseCommand):
    help = 'Lite Edition: simple Urdu-first mode for small shops (on / off / status)'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['on', 'off', 'status'])
        parser.add_argument('--also', nargs='*', default=[], metavar='MODULE',
                            help='extra modules to keep ON (%s)' % ' '.join(LITE_OPTIONAL))
        parser.add_argument('--lang', default=LITE_DEFAULT_LANG, choices=['ur', 'en', 'ar'],
                            help='default language while Lite is ON (default: ur)')

    def handle(self, *args, **opts):
        action = opts['action']
        is_on = SystemSetting.objects.filter(setting_key=LITE_MARKER).exists()

        if action == 'status':
            self.stdout.write('Lite Edition: %s' % ('ON' if is_on else 'OFF'))
            self.stdout.write('business_mode = %s' % SystemSetting.get_value('business_mode', 'both'))
            if is_on:
                self.stdout.write('default language = %s' % SystemSetting.get_value(LITE_LANG_KEY, LITE_DEFAULT_LANG))
            return

        if action == 'on':
            if is_on:
                self.stdout.write(self.style.WARNING(
                    'Lite is already ON. Run `lite_edition off` first to change the module list.'))
                return
            try:
                show, hide = enable_lite(opts['also'], opts['lang'])
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write(self.style.SUCCESS('Lite Edition ON.'))
            self.stdout.write('Visible : ' + ', '.join(show))
            self.stdout.write('Hidden  : ' + ', '.join(hide))
            self.stdout.write('Reload the browser. Undo: python manage.py lite_edition off')
            return

        if disable_lite():
            self.stdout.write(self.style.SUCCESS('Lite Edition OFF. Previous module settings restored.'))
        else:
            self.stdout.write(self.style.WARNING('Lite Edition is not ON.'))
