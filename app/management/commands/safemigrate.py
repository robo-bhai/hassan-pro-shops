import datetime
import os
import sqlite3

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

COUNT_TABLES = [
    "auth_user", "app_product", "app_customer", "app_vendor", "app_sale", "app_saleitem",
    "app_purchase", "app_purchaseitem", "app_inventory", "app_stockbatch", "app_employee",
    "app_shareholder", "app_journalentry", "app_cashtransaction", "app_client",
]


def classify_operation(op):
    name = op.__class__.__name__
    if name == "DeleteModel":
        return "DANGER", f"DeleteModel {op.name}: poori table delete hogi, us ka saara data jayega"
    if name == "RemoveField":
        return "DANGER", f"RemoveField {op.model_name}.{op.name}: column delete hoga, us column ka data jayega"
    if name == "SeparateDatabaseAndState":
        for sub in getattr(op, "database_operations", []) or []:
            found = classify_operation(sub)
            if found:
                return found
        return None
    if name in ("RunSQL", "RunPython"):
        return "CHECK", f"{name}: custom code hai, migration file khud padh kar dekhein"
    if name in ("RenameModel", "RenameField", "AlterModelTable"):
        return "CHECK", f"{name}: rename hai (data rehna chahiye), phir bhi dekh lein"
    return None


def scan_plan(plan):
    findings = []
    for migration, backwards in plan:
        if backwards:
            findings.append(("DANGER", f"{migration.app_label}.{migration.name}", "ULTI (backwards) migration chal rahi hai"))
            continue
        for op in migration.operations:
            found = classify_operation(op)
            if found:
                findings.append((found[0], f"{migration.app_label}.{migration.name}", found[1]))
    return findings


def table_counts(vendor_tables, cursor):
    out = {}
    for t in COUNT_TABLES:
        if t in vendor_tables:
            cursor.execute('SELECT COUNT(*) FROM "%s"' % t)
            out[t] = cursor.fetchone()[0]
    return out


def sqlite_backup(src, folder, stamp):
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"pre_migrate_{stamp}.sqlite3")
    s, d = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    if os.path.getsize(dest) == 0:
        raise RuntimeError("Backup file khali bani")
    return dest


class Command(BaseCommand):
    help = "Backup + jaanch ke saath migrate (data na udne ke liye)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Sirf report dikhao")
        parser.add_argument("--allow-destructive", action="store_true",
                            help="Table/column delete karne wali migrations ki ijazat")

    def _counts(self):
        with connection.cursor() as cur:
            return table_counts(set(connection.introspection.table_names(cur)), cur)

    def handle(self, *args, **opts):
        out = self.stdout.write
        cfg = connection.settings_dict
        out(self.style.MIGRATE_HEADING("== Database"))
        out(f"   engine : {connection.vendor}")
        out(f"   naam   : {cfg.get('NAME')}")
        before = self._counts()
        for t, n in before.items():
            out(f"   {t:22s} {n}")

        executor = MigrationExecutor(connection)
        conflicts = executor.loader.detect_conflicts()
        if conflicts:
            raise CommandError(f"Migration conflict (do leaf nodes): {conflicts}. Pehle 'makemigrations --merge' chalayein.")
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            out(self.style.SUCCESS("\nKoi pending migration nahi. Kuch karne ki zaroorat nahi."))
            return

        out(self.style.MIGRATE_HEADING("\n== Pending migrations"))
        for migration, backwards in plan:
            out(f"   {'<-' if backwards else '->'} {migration.app_label}.{migration.name}")

        findings = scan_plan(plan)
        danger = [f for f in findings if f[0] == "DANGER"]
        if findings:
            out(self.style.MIGRATE_HEADING("\n== Jaanch"))
            for level, mig, text in findings:
                line = f"   [{level}] {mig}: {text}"
                out(self.style.ERROR(line) if level == "DANGER" else self.style.WARNING(line))
        else:
            out(self.style.SUCCESS("\n   Koi table/column delete karne wali migration nahi."))

        if opts["dry_run"]:
            out("\n--dry-run: kuch nahi badla.")
            return
        if danger and not opts["allow_destructive"]:
            raise CommandError(
                "Ye migrations data delete karengi, is liye RUK gaya. Pehle un tables ka data nikaal lein "
                "(ya migration badlein). Jaan boojh kar karna ho to: python manage.py safemigrate --allow-destructive")

        backup = None
        if connection.vendor == "sqlite":
            folder = getattr(settings, "BACKUP_DIR", None) or os.path.join(str(settings.BASE_DIR), "dbbackup")
            backup = sqlite_backup(str(cfg["NAME"]), folder, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            out(self.style.SUCCESS(f"\nBackup bani: {backup}"))
        else:
            out(self.style.WARNING("\nYe SQLite nahi hai: mysqldump / pg_dump se apni backup pehle khud le lein."))

        call_command("migrate", interactive=False)

        after = self._counts()
        lost = {t: (before[t], after.get(t, 0)) for t in before if after.get(t, 0) < before[t]}
        out(self.style.MIGRATE_HEADING("\n== Migrate ke baad rows"))
        for t, n in after.items():
            out(f"   {t:22s} {n}")
        if lost:
            out(self.style.ERROR("\nWARNING: in tables mein rows kam ho gayi (pehle -> ab): " + str(lost)))
            if backup:
                out(self.style.ERROR(f"Wapas lene ke liye backup: {backup}"))
        else:
            out(self.style.SUCCESS("\nSab theek: kisi table ki rows kam nahi hui."))
