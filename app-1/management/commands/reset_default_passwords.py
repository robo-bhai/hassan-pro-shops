from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Find accounts that still use the old default password 'password123' (or are listed with --also) "
        "and lock them. Use --apply to really change them (dry run by default)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Lock the weak accounts (default: only list them).")
        parser.add_argument("--also", nargs="*", default=[], help="Extra weak passwords to test.")

    def handle(self, *args, **options):
        User = get_user_model()
        weak = ["password123"] + list(options["also"])
        found = []
        for user in User.objects.filter(is_active=True).iterator():
            if any(user.check_password(p) for p in weak):
                found.append(user)
        if not found:
            self.stdout.write(self.style.SUCCESS("No account uses a weak default password."))
            return
        for user in found:
            self.stdout.write(f"  weak password: {user.username} (superuser={user.is_superuser})")
            if options["apply"]:
                user.set_unusable_password()
                user.save(update_fields=["password"])
        if options["apply"]:
            self.stdout.write(self.style.WARNING(
                f"{len(found)} account(s) locked. Set a new password for each from the shareholder edit page "
                "(or `python manage.py changepassword <username>`)."))
        else:
            self.stdout.write(self.style.WARNING(f"{len(found)} weak account(s). Run again with --apply to lock them."))
