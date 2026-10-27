"""python manage.py setup_stores  -> PMS, RMS, FGS, Technical stores are created (safe to run again)."""
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import StoreProfile, Warehouse

DEFAULT_STORES = [
    ('PMS', 'PMS - Packing Material Store', 'PMS', 'Packing material: cartons, bottles, labels, bags, tape'),
    ('RMS', 'RMS - Raw Material Store', 'RMS', 'Raw material used in production'),
    ('FGS', 'FGS - Finished Goods Store', 'FGS', 'Finished goods (for sale)'),
    ('TECH', 'Technical Store', 'TECH', 'Spare parts, tools, maintenance aur workshop items'),
]


class Command(BaseCommand):
    help = "Creates the default stores (PMS, RMS, FGS, Technical). Does not touch existing ones."

    def add_arguments(self, parser):
        parser.add_argument("--tag-existing", action="store_true",
                            help="Tag warehouses that have no store profile as General (GEN)")

    @transaction.atomic
    def handle(self, *args, **o):
        for code, name, stype, desc in DEFAULT_STORES:
            wh, created = Warehouse.objects.get_or_create(name=name, defaults={'description': desc})
            prof, pcreated = StoreProfile.objects.get_or_create(
                warehouse=wh, defaults={'code': code, 'store_type': stype})
            self.stdout.write(f"{'created' if created else 'exists '}  {wh.name}"
                              f"{'  (+profile)' if pcreated else ''}")
        if o["tag_existing"]:
            n = 0
            for wh in Warehouse.objects.filter(store_profile__isnull=True):
                base = f"GEN{wh.pk}"
                StoreProfile.objects.create(warehouse=wh, code=base, store_type='GEN')
                n += 1
            self.stdout.write(f"tagged {n} existing warehouse(s) as General")
        self.stdout.write(self.style.SUCCESS("Stores ready."))
