"""Shop Edition switch (online shop order process ke liye sirf zaroori modules).

Yeh wahi switch hai jo Settings > Modules > Edition card mein "Shop" ke naam se hai
(Full ERP / Lite / Shop). Command sirf shell se chalane ke liye hai.

  python manage.py shop_edition status
  python manage.py shop_edition on
  python manage.py shop_edition on --also installment     # extra module bhi ON rakho
  python manage.py shop_edition on --only-core            # sirf zaroori 5 modules
  python manage.py shop_edition off                       # pehli settings wapas

Kuch delete nahi hota: sirf module visibility (SystemSetting, "Shop" switch) badalti hai.
Pehli values shop_edition_prev_state.json mein save hoti hain, `off` sab wapas kar deta hai.
"""
from django.core.management.base import BaseCommand, CommandError

from app.lite_edition import (SHOP_CORE, SHOP_OPTIONAL, SHOP_OPTIONAL_ON, disable_shop, enable_shop,
                              shop_marker_on)
from app.models import SystemSetting


class Command(BaseCommand):
    help = 'Shop Edition: online shop order process ke modules on / off / status'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['on', 'off', 'status'])
        parser.add_argument('--also', nargs='*', default=[], metavar='MODULE',
                            help='extra modules ON rakho (jaise: %s)' % ' '.join(SHOP_OPTIONAL))
        parser.add_argument('--roles', nargs='*', default=[], metavar='ROLE',
                            help='Shop sirf in roles par lagao (jaise: salesman warehouse); baqi roles ko poora menu')
        parser.add_argument('--only-core', action='store_true',
                            help='sirf zaroori modules ON (%s)' % ' '.join(SHOP_CORE))

    def handle(self, *args, **opts):
        action = opts['action']
        is_on = shop_marker_on()

        if action == 'status':
            self.stdout.write('Shop Edition: %s' % ('ON' if is_on else 'OFF'))
            self.stdout.write('business_mode = %s' % SystemSetting.get_value('business_mode', 'both'))
            from app.lite_edition import shop_roles_now
            self.stdout.write('roles = %s' % (', '.join(shop_roles_now()) or 'sab'))
            return

        if action == 'on':
            if is_on:
                self.stdout.write(self.style.WARNING(
                    'Shop Edition pehle se ON hai. Module list badalni ho to pehle `shop_edition off` chalayein.'))
                return
            try:
                show, hide = enable_shop([m.strip().lower() for m in opts['also']], opts['only_core'], opts['roles'])
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write(self.style.SUCCESS('Shop Edition ON.'))
            self.stdout.write('Visible : ' + ', '.join(show))
            self.stdout.write('Hidden  : ' + ', '.join(hide))
            self.stdout.write('Browser reload karein. Undo: python manage.py shop_edition off')
            return

        if disable_shop():
            self.stdout.write(self.style.SUCCESS('Shop Edition OFF. Pehli module settings wapas aa gayi.'))
        else:
            self.stdout.write(self.style.WARNING('Shop Edition ON nahi hai.'))
