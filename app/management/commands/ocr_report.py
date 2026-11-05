"""python manage.py ocr_report [--days 30] : how well the camera product search works."""
from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import OcrAliasSuggestion, OcrScanLog


class Command(BaseCommand):
    help = 'OCR accuracy report from OcrScanLog'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **o):
        since = timezone.now() - timedelta(days=o['days'])
        rows = list(OcrScanLog.objects.filter(created_at__gte=since).values_list('outcome', 'text', 'top_score'))
        total = len(rows)
        self.stdout.write('OCR scans in the last %d days: %d' % (o['days'], total))
        if not total:
            return
        c = Counter(r[0] for r in rows)
        for k, label in OcrScanLog.OUTCOMES:
            self.stdout.write('  %-12s %5d  %5.1f%%' % (k, c.get(k, 0), 100.0 * c.get(k, 0) / total))
        decided = c['auto_added'] + c['tapped_top'] + c['corrected']
        if decided:
            ok = c['auto_added'] + c['tapped_top']
            self.stdout.write('First match was right: %.1f%% of %d decided scans' % (100.0 * ok / decided, decided))
        miss = Counter(r[1] for r in rows if r[0] == 'no_match').most_common(10)
        if miss:
            self.stdout.write('Most common texts with NO product:')
            for t, n in miss:
                self.stdout.write('  %3d x %s' % (n, t))
        pend = OcrAliasSuggestion.objects.filter(status='pending').count()
        self.stdout.write('Alias suggestions waiting: %d (Admin > OCR alias suggestions)' % pend)
