from django.core.management.base import BaseCommand

from app.models import ShareholderLoginRequest


class Command(BaseCommand):
    help = "Erase plain-text passwords that older versions saved in ShareholderLoginRequest.generated_password."

    def handle(self, *args, **options):
        qs = ShareholderLoginRequest.objects.exclude(generated_password__isnull=True).exclude(generated_password="")
        count = qs.count()
        qs.update(generated_password=None)
        self.stdout.write(self.style.SUCCESS(f"Cleared {count} stored password(s)."))
