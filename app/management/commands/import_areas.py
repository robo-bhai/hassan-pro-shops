"""python manage.py import_areas areas.csv   (har line: city,area)"""
import csv

from django.core.management.base import BaseCommand, CommandError

from app.models import DeliveryArea


class Command(BaseCommand):
    help = "CSV (city,area) se DeliveryArea list import karta hai. Dohraye hue skip ho jate hain."

    def add_arguments(self, parser):
        parser.add_argument('csv_file')

    def handle(self, *args, **opts):
        made = skipped = 0
        try:
            f = open(opts['csv_file'], newline='', encoding='utf-8-sig')
        except OSError as exc:
            raise CommandError(str(exc))
        with f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                city, name = ' '.join(row[0].split())[:100], ' '.join(row[1].split())[:100]
                if not city or not name or city.lower() == 'city':
                    continue
                _, created = DeliveryArea.objects.get_or_create(city=city, name=name)
                made += created
                skipped += (not created)
        self.stdout.write(self.style.SUCCESS(f"{made} nayi areas add hui, {skipped} pehle se mojood thin."))
