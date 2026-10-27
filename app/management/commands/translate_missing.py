from django.core.management.base import BaseCommand

from app.i18n import i18n_service as svc


class Command(BaseCommand):
    help = "Machine-translate English UI text that has no Urdu/Arabic yet (never overwrites manual/reviewed text)."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=40)

    def handle(self, *args, **opts):
        svc.ensure_seeded()
        r = svc.translate_pending(opts['limit'])
        self.stdout.write('provider=%(provider)s translated=%(translated)s pending=%(pending)s' % r)
        if r['error']:
            self.stderr.write('error: ' + r['error'])
