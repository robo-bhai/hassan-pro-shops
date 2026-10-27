"""Agri Edition alerts (run once a day, e.g. from cron / Task Scheduler).

  python manage.py agri_alerts                  # in-app notification to staff + summary on screen
  python manage.py agri_alerts --csv out.csv    # also save overdue farmers with ready WhatsApp links
  python manage.py agri_alerts --dry-run        # only print, send nothing

One notification per staff user per day (running it twice does not repeat it).
"""
import csv

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from app.agri import views as agri
from app.models import Notification


class Command(BaseCommand):
    help = 'Agri Edition: expiry + overdue farmer alerts'

    def add_arguments(self, parser):
        parser.add_argument('--csv', help='write overdue farmers (with WhatsApp links) to this file')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        buckets = agri._expiry_buckets()
        rows = agri._farmers()
        summary = agri._summary(rows)
        today = timezone.localdate()

        lines = []
        if buckets['expired']['count']:
            lines.append('%d batch expire ho chuke (Rs. %s).' % (buckets['expired']['count'],
                                                                 format(int(buckets['expired']['value']), ',')))
        if buckets['d30']['count']:
            lines.append('%d batch 30 din mein expire honge (Rs. %s).' % (buckets['d30']['count'],
                                                                         format(int(buckets['d30']['value']), ',')))
        if buckets['missing']['count']:
            lines.append('%d batch par expiry date nahi daali.' % buckets['missing']['count'])
        if summary['overdue_farmers']:
            lines.append('%d kisan ki wapsi ki tareekh guzar gayi (Rs. %s).' % (
                summary['overdue_farmers'], format(int(summary['overdue_total']), ',')))
        if summary['week_farmers']:
            lines.append('%d kisan ki wapsi is hafte hai.' % summary['week_farmers'])
        if summary['over_limit']:
            lines.append('%d kisan credit limit se aage hain.' % summary['over_limit'])

        if not lines:
            self.stdout.write(self.style.SUCCESS('Sab theek hai, koi alert nahi.'))
        else:
            for ln in lines:
                self.stdout.write(' - ' + ln)

        if opts['csv']:
            late = [r for r in rows if r['is_overdue']]
            with open(opts['csv'], 'w', newline='', encoding='utf-8-sig') as fh:
                w = csv.writer(fh)
                w.writerow(['Kisan', 'Gaon', 'Phone', 'Baqaya', 'Wapsi ki tareekh', 'Din guzre', 'WhatsApp link'])
                for r in late:
                    c = r['customer']
                    w.writerow([c.name, c.village or '', c.contact_number or '', int(r['balance']),
                                r['next_due'].strftime('%d-%m-%Y') if r['next_due'] else '',
                                r['days_abs'] or '', r['wa']])
            self.stdout.write('%d overdue kisan %s mein save huye.' % (len(late), opts['csv']))

        if not lines or opts['dry_run']:
            return
        title = 'Agri alert %s' % today.strftime('%d-%m-%Y')
        sent = 0
        staff = User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(is_staff=True))
        for u in staff:
            if Notification.objects.filter(user=u, title=title).exists():
                continue
            Notification.send(u, title, '\n'.join(lines), notification_type='warning', category='stock',
                              link='/agri/')
            sent += 1
        self.stdout.write(self.style.SUCCESS('%d staff ko notification bheji.' % sent))
