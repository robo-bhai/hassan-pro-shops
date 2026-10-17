"""
python manage.py backup_db run            # full backup (cron uses this)
python manage.py backup_db run --no-cloud
python manage.py backup_db list
python manage.py backup_db verify [file]  # default: newest
python manage.py backup_db restore <file> [--yes]
python manage.py backup_db prune
python manage.py backup_db status         # exit code 1 if backups are stale (monitoring)
"""
import sys

from django.core.management.base import BaseCommand, CommandError

from app import backup_service as bs


class Command(BaseCommand):
    help = "Professional backup system: run / list / verify / restore / prune / status"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["run", "list", "verify", "restore",
                                               "prune", "status"])
        parser.add_argument("file", nargs="?")
        parser.add_argument("--no-cloud", action="store_true")
        parser.add_argument("--no-media", action="store_true")
        parser.add_argument("--yes", action="store_true", help="skip restore confirmation")
        parser.add_argument("--with-media", action="store_true", help="restore: also restore media/ files")

    def handle(self, *a, **o):
        act = o["action"]
        try:
            getattr(self, f"do_{act}")(o)
        except bs.BackupError as e:
            raise CommandError(str(e))

    def do_run(self, o):
        m = bs.create_backup(upload=not o["no_cloud"], include_media=not o["no_media"],
                             trigger="cron")
        self.stdout.write(self.style.SUCCESS(m["message"]))

    def do_list(self, o):
        for b in bs.list_backups():
            v = {True: "verified", False: "BAD", None: "?"}[b["verified"]]
            self.stdout.write(f'{b["name"]:48} {b["size_display"]:>9}  {b["modified"]}  [{v}]')

    def do_verify(self, o):
        files = [o["file"]] if o["file"] else [bs.list_backups()[0]["name"]] if bs.list_backups() else []
        if not files:
            raise CommandError("No backups found.")
        ok_all = True
        for f in files:
            ok, msg = bs.verify_backup(bs.resolve_local(f))
            ok_all &= ok
            self.stdout.write((self.style.SUCCESS if ok else self.style.ERROR)(f"{f}: {msg}"))
        if not ok_all:
            sys.exit(1)

    def do_restore(self, o):
        if not o["file"]:
            raise CommandError("Give a backup file name (see: backup_db list).")
        path = bs.resolve_local(o["file"])
        if not o["yes"]:
            ans = input(f"This will OVERWRITE the current database with {path.name}. "
                        "Type RESTORE to continue: ")
            if ans.strip() != "RESTORE":
                raise CommandError("Cancelled.")
        safety = bs.restore_backup(path)
        self.stdout.write(self.style.SUCCESS(f"Restored. Safety copy of old DB: {safety}"))
        if o["with_media"]:
            self.stdout.write(self.style.SUCCESS(f"Media restored from: {bs.restore_media(path)}"))

    def do_prune(self, o):
        d = bs.prune_local()
        self.stdout.write(f"Deleted {len(d)} old backup(s): {', '.join(d) or '-'}")

    def do_status(self, o):
        h = bs.health()
        self.stdout.write(str(h))
        if not h["healthy"]:
            self.stderr.write(self.style.ERROR("BACKUP UNHEALTHY / STALE"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("Backups healthy."))
