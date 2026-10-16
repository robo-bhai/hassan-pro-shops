from django.core.management.base import BaseCommand

from app import auto_tester


class Command(BaseCommand):
    help = "Run the automatic system tests and store the results in the Testing module."

    def add_arguments(self, parser):
        parser.add_argument("--no-pages", action="store_true", help="Skip the page-by-page check (faster).")

    def handle(self, *args, **opts):
        summary = auto_tester.run_all(include_pages=not opts["no_pages"])
        for r in summary["results"]:
            mark = self.style.SUCCESS("PASS") if r.status == "passed" else self.style.ERROR("FAIL")
            self.stdout.write(f"[{mark}] {r.suite} / {r.title} - {r.actual}")
            for sev, name, msg in r.details:
                self.stdout.write(f"        ({sev}) {name}: {msg}")
        self.stdout.write(
            f"\nTotal {summary['total']} | Passed {summary['passed']} | Failed {summary['failed']} | "
            f"Warnings {summary['warnings']} | New bugs {summary['new_bugs']}")
