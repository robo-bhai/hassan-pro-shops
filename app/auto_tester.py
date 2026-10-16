"""
Automatic system tester for the Testing module.

What it does (read-only on your data - every page request is rolled back):
  1. Django system check            -> configuration / model errors
  2. Pending migrations             -> database out of sync with models
  3. Database tables                -> every model's table is readable (missing column/table)
  4. Templates                      -> every .html template compiles (syntax errors)
  5. Pages                          -> every URL without parameters opens (no 500 error, not slow)
  6. Custom checks                  -> your own business rules (see CUSTOM CHECKS at the bottom)

Results are stored in the Testing module itself:
  TestProject "System Auto Tests" -> TestSuite -> TestCase -> TestExecution,
  and every real failure becomes a Bug (no duplicates while the same bug is still open).

Run from the web (Testing dashboard -> "Run Auto Tests") or from the terminal:
    python manage.py run_auto_tests
"""
import json
import os
import tempfile
import threading
import time
import traceback
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import checks
from django.db import connection, transaction
from django.template import engines
from django.template.exceptions import TemplateDoesNotExist, TemplateSyntaxError
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone

from app.models import Bug, TestCase, TestExecution, TestProject, TestSuite

PROJECT_NAME = "System Auto Tests"
MAX_BUGS_PER_CHECK = 25          # a broken system must not flood the bug list

# Pages that must NEVER be opened by the tester (they act on GET, cost money, or call outside services)
SKIP_URL_WORDS = (
    "delete", "remove", "logout", "signout", "backup", "restore", "reset", "clear", "purge",
    "send", "whatsapp", "sms", "email", "notify", "sync", "upload", "import", "process",
    "two-factor", "2fa", "mfa", "otp", "approve", "reject", "cancel", "close", "generate", "run-auto", "auto-test", "bulk",
    "ai/", "/ai-", "stream", "/live", "-live", "webhook", "callback", "download", "export", "pdf",
    "toggle", "mark-", "execute", "payment", "pay/", "checkout", "buy-now", "add-to-cart",
)
_note_cb = None                  # set by the background worker to show "Pages: 120/300"


class RunCancelled(Exception):
    """Raised when the user pressed Stop."""


def _check_cancel():
    try:
        if _read_state().get("cancel"):
            raise RunCancelled()
    except RunCancelled:
        raise
    except Exception:
        pass


def _note(text):
    if _note_cb:
        try:
            _note_cb(text)
        except Exception:
            pass


SLOW_SECONDS = 3.0
MAX_PAGES = 400


# --------------------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------------------
class CheckResult:
    def __init__(self, suite, title, description, expected):
        self.suite, self.title, self.description, self.expected = suite, title, description, expected
        self.status = "passed"          # passed | failed
        self.actual = ""
        self.details = []               # list of (severity, name, message)
        self.started = time.monotonic()
        self.duration = timedelta(0)

    def fail(self, name, message, severity="major"):
        self.status = "failed"
        self.details.append((severity, name, message))

    def warn(self, name, message):
        self.details.append(("warning", name, message))

    def finish(self):
        self.duration = timedelta(seconds=time.monotonic() - self.started)
        failures = [d for d in self.details if d[0] != "warning"]
        warns = [d for d in self.details if d[0] == "warning"]
        if self.status == "passed":
            self.actual = "OK" + (f" ({len(warns)} warning(s))" if warns else "")
        else:
            self.actual = f"{len(failures)} problem(s) found"


# --------------------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------------------
def check_django_system():
    r = CheckResult("System", "Django system check",
                    "Runs Django's built-in checks over settings, models, admin and URLs.",
                    "No errors reported.")
    try:
        for m in checks.run_checks():
            if m.level >= checks.ERROR:
                r.fail(m.id, str(m.msg), "critical")
            elif m.level >= checks.WARNING:
                r.warn(m.id, str(m.msg))
    except Exception as e:
        r.fail("system-check", f"System check crashed: {e}", "critical")
    r.finish()
    return r


def check_migrations():
    r = CheckResult("System", "Pending database migrations",
                    "Compares migration files with the database.",
                    "Database is fully migrated.")
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        for migration, _backwards in plan:
            r.fail(str(migration), "Migration not applied. Run: python manage.py migrate", "critical")
    except Exception as e:
        r.fail("migrations", f"Could not read migration state: {e}", "major")
    r.finish()
    return r


def check_database_tables():
    r = CheckResult("Database", "All model tables readable",
                    "Reads one row from every model table to detect missing tables/columns.",
                    "Every table can be queried.")
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        label = model._meta.label
        try:
            with transaction.atomic():
                list(model._default_manager.all()[:1])
        except Exception as e:
            r.fail(label, f"{type(e).__name__}: {str(e)[:300]}", "critical")
    r.finish()
    return r


def check_database_integrity():
    r = CheckResult("Database", "Data integrity (no broken links between records)",
                    "Looks for records that point to a parent record that no longer exists, and checks the database file itself.",
                    "No orphaned records and the database file is healthy.")
    try:
        if connection.vendor == "sqlite":
            with connection.cursor() as cur:
                cur.execute("PRAGMA integrity_check")
                verdict = [str(row[0]) for row in cur.fetchall()]
                if verdict != ["ok"]:
                    r.fail("database file", "SQLite integrity_check: " + "; ".join(verdict)[:300], "critical")
                cur.execute("PRAGMA foreign_key_check")
                rows = cur.fetchmany(5000)
            groups = {}
            for table, rowid, parent, _fk in rows:
                g = groups.setdefault((table, parent), [0, rowid])
                g[0] += 1
            for (table, parent), (count, sample) in sorted(groups.items()):
                r.fail(f"{table} -> {parent}",
                       f"{count} record(s) in '{table}' point to a missing '{parent}' record (example row id: {sample}).",
                       "major")
        else:
            connection.check_constraints()
    except Exception as e:
        r.fail("integrity check", f"{type(e).__name__}: {str(e)[:300]}", "major")
    r.finish()
    return r


def _template_names():
    seen = set()
    dirs = []
    for conf in settings.TEMPLATES:
        dirs.extend(conf.get("DIRS", []))
    for cfg in apps.get_app_configs():
        dirs.append(f"{cfg.path}/templates")
    import os
    for base in dirs:
        base = str(base)
        if not os.path.isdir(base):
            continue
        for root, _d, files in os.walk(base):
            for f in files:
                if f.endswith(".html"):
                    full = os.path.join(root, f)
                    name = os.path.relpath(full, base).replace(os.sep, "/")
                    # skip Django's own admin/auth templates
                    if name.startswith(("admin/", "registration/")):
                        continue
                    seen.add(name)
    return sorted(seen)


def check_templates():
    r = CheckResult("Templates", "All templates compile",
                    "Loads every HTML template and checks Django template syntax.",
                    "No template syntax errors.")
    engine = engines["django"]
    names = _template_names()
    for name in names:
        try:
            engine.get_template(name)
        except TemplateSyntaxError as e:
            r.fail(name, f"Template syntax error: {e}", "major")
        except TemplateDoesNotExist as e:
            r.fail(name, f"Template includes/extends a missing file: {e}", "major")
        except Exception as e:
            r.fail(name, f"{type(e).__name__}: {e}", "major")
    r.actual_extra = f"{len(names)} templates scanned"
    r.finish()
    if r.status == "passed":
        r.actual = f"OK - {len(names)} templates scanned"
    return r


def _iter_urls(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _iter_urls(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p


def _clean_route(route):
    return route.replace("^", "").replace("$", "").replace("\\", "")


def check_pages(user, host):
    r = CheckResult("Pages", "Every page opens without error",
                    "Opens every parameter-free URL as the logged-in superuser (changes are rolled back).",
                    "No page returns a 5xx error or crashes.")
    client = Client(raise_request_exception=False, HTTP_HOST=host)
    client.force_login(user)

    urls = []
    for route, _p in _iter_urls(get_resolver().url_patterns):
        route = _clean_route(route)
        if "<" in route or "(" in route or "?P" in route:      # needs parameters -> skip
            continue
        low = "/" + route.lower()
        if low.startswith("/admin"):                         # Django admin has its own tests
            continue
        if any(w in low for w in SKIP_URL_WORDS):
            continue
        urls.append("/" + route.lstrip("/"))
    urls = sorted(set(urls))[:MAX_PAGES]

    r.checked = set(urls)            # lets _store() know which pages were really tested
    from collections import Counter
    causes = Counter()               # same error on many pages = one root cause
    timings = []                     # (seconds, url) of pages that answered
    ok = redirects = missing = 0
    for i, url in enumerate(urls, 1):
        _check_cancel()
        if i % 10 == 1 or i == len(urls):
            _note(f"Pages: {i}/{len(urls)}")
        resp = err = None
        for attempt in (1, 2):                            # a 5xx must repeat once before it counts
            t = time.monotonic()
            try:
                with transaction.atomic():
                    resp = client.get(url, follow=False)
                    transaction.set_rollback(True)        # undo anything a GET view might write
                err = None
            except Exception as e:
                resp, err = None, e
            if err is None and resp.status_code < 500:
                break
            if attempt == 1:
                time.sleep(0.3)
        took = time.monotonic() - t
        if err is not None:
            msg = f"Crashed: {type(err).__name__}: {str(err)[:300]}"
            causes[msg] += 1
            r.fail(url, msg, "major")
            continue
        code = resp.status_code
        if code >= 500:
            exc = getattr(resp, "exc_info", None)
            msg = f"HTTP {code}"
            if exc and exc[1]:
                msg += f" - {type(exc[1]).__name__}: {str(exc[1])[:300]}"
                try:
                    frames = [fr for fr in traceback.extract_tb(exc[2])
                              if "site-packages" not in fr.filename]
                    if frames:
                        msg += f" [{os.path.basename(frames[-1].filename)}:{frames[-1].lineno}]"
                except Exception:
                    pass
            if "database is locked" in msg:
                r.warn(url, "SQLite was busy (another request was writing): " + msg)
            else:
                causes[msg.split(" [")[0]] += 1
                r.fail(url, msg, "major")
        elif code == 404:
            missing += 1
            r.warn(url, "HTTP 404 (URL exists in urls.py but page says not found)")
        else:
            redirects += 1 if 300 <= code < 400 else 0
            ok += 1 if code < 400 else 0
            body = b"" if getattr(resp, "streaming", False) else (resp.content or b"")[:300000]
            if code == 200 and b"Traceback (most recent call last)" in body:
                msg = "Page shows a Python traceback (HTTP 200)"
                causes[msg] += 1
                r.fail(url, msg, "major")
        if code < 500:
            timings.append((took, url))
        if took > SLOW_SECONDS and code < 500:
            r.warn(url, f"Slow page: {took:.1f}s")
    r.actual_extra = f"{len(urls)} pages tried"
    r.finish()
    if r.status == "failed" and causes:
        top, n = causes.most_common(1)[0]
        r.actual += f" - most common cause ({n}x): {top[:160]}"
    r.slowest = [{"url": u, "seconds": round(t, 2)} for t, u in sorted(timings, reverse=True)[:3]]
    if r.status == "passed":
        r.actual = f"OK - {len(urls)} pages tried ({ok} ok, {redirects} redirects, {missing} not found)"
    return r


# --------------------------------------------------------------------------------------
# CUSTOM CHECKS - add your own business rules here.
# Each function returns a CheckResult. Example (adjust field names to your models):
#
# def check_trial_balance():
#     r = CheckResult("Accounts", "Trial balance: debit = credit",
#                     "Total debits must equal total credits.", "Difference is zero.")
#     from django.db.models import Sum
#     from app.models import JournalEntryLine
#     d = JournalEntryLine.objects.aggregate(d=Sum("debit"), c=Sum("credit"))
#     if (d["d"] or 0) != (d["c"] or 0):
#         r.fail("trial-balance", f"Debit {d['d']} != Credit {d['c']}", "critical")
#     r.finish()
#     return r
# --------------------------------------------------------------------------------------
CUSTOM_CHECKS = [
    # check_trial_balance,
]


# --------------------------------------------------------------------------------------
# Saving results inside the Testing module
# --------------------------------------------------------------------------------------
CLOSED_STATUSES = ["fixed", "verified", "closed", "duplicate", "won_fix"]


def _auto_close_resolved(result, case, real):
    """Old [Auto] bugs of this check whose problem is no longer reported are marked 'fixed'.
    Only bugs the check really re-tested are touched; anything uncertain stays open."""
    if any(d[1] == "crash" for d in real):          # the checker itself crashed -> we know nothing
        return 0
    suffix = f" - {result.title}"
    still = {f"[Auto] {name}{suffix}"[:200] for _sev, name, _msg in real}
    unsure = {f"[Auto] {name}{suffix}"[:200] for sev, name, msg in result.details
              if sev == "warning" and "SQLite was busy" in str(msg)}
    checked = getattr(result, "checked", None)       # None = every problem is re-tested each run
    summary_prefix = f"[Auto] {result.title}: "
    closed = 0
    open_bugs = Bug.objects.filter(test_case=case, title__startswith="[Auto] ").exclude(status__in=CLOSED_STATUSES)
    for bug in open_bugs:
        if bug.title in still or bug.title in unsure:
            continue
        if bug.title.startswith(summary_prefix):
            if len(real) > MAX_BUGS_PER_CHECK:
                continue
        elif checked is not None:
            if not bug.title.endswith(suffix) or bug.title[7:-len(suffix)] not in checked:
                continue                              # page was not opened this run -> cannot say it is fixed
        bug.status = "fixed"
        bug.save(update_fields=["status"])
        closed += 1
    return closed


def _store(result, user):
    project, _ = TestProject.objects.get_or_create(
        name=PROJECT_NAME,
        defaults={"description": "Created automatically by the Auto Tester.",
                  "version": "auto", "start_date": timezone.localdate(), "created_by": user},
    )
    suite, _ = TestSuite.objects.get_or_create(project=project, name=result.suite)
    case, _ = TestCase.objects.get_or_create(
        suite=suite, title=result.title,
        defaults={"description": result.description, "expected_result": result.expected,
                  "test_type": "integration", "priority": "high", "is_automated": True,
                  "test_steps": ["Run the auto tester"], "created_by": user},
    )
    now = timezone.now()
    case.status = result.status
    case.actual_result = result.actual
    case.executed_by = user
    case.executed_at = now
    case.execution_time = result.duration
    case.is_automated = True
    case.save()

    TestExecution.objects.create(
        test_case=case, executed_by=user, status=result.status, completed_at=now,
        duration=result.duration, notes=result.actual,
        results={"details": [{"severity": s, "item": n, "message": m} for s, n, m in result.details][:500]},
    )

    bugs = 0
    real = [d for d in result.details if d[0] != "warning"]
    for severity, name, message in real[:MAX_BUGS_PER_CHECK]:
        title = f"[Auto] {name} - {result.title}"[:200]
        exists = Bug.objects.filter(title=title).exclude(
            status__in=["fixed", "verified", "closed", "duplicate", "won_fix"]).exists()
        if exists:
            continue
        reopen = Bug.objects.filter(title=title, status__in=["fixed", "verified", "closed"]).first()
        if reopen:
            reopen.status = "reopened"
            reopen.save(update_fields=["status"])
            continue
        Bug.objects.create(
            title=title, description=message, severity="critical" if severity == "critical" else "major",
            module=result.suite, test_case=case, reported_by=user, status="new",
            steps_to_reproduce=f"Run Auto Tests -> '{result.title}'", actual_result=message,
            expected_result=result.expected,
        )
        bugs += 1
    if len(real) > MAX_BUGS_PER_CHECK:
        title = f"[Auto] {result.title}: {len(real)} problems (first {MAX_BUGS_PER_CHECK} reported separately)"[:200]
        if not Bug.objects.filter(title=title).exists():
            Bug.objects.create(
                title=title, description="See the latest execution of this test case for the full list.",
                severity="major", module=result.suite, test_case=case, reported_by=user, status="new",
                steps_to_reproduce=f"Run Auto Tests -> '{result.title}'", actual_result=result.actual,
                expected_result=result.expected)
            bugs += 1
    closed = _auto_close_resolved(result, case, real)
    return bugs, closed


def _runners(user, host, include_pages):
    items = [
        ("Django system check", check_django_system),
        ("Pending migrations", check_migrations),
        ("Database tables", check_database_tables),
        ("Data integrity", check_database_integrity),
        ("Templates", check_templates),
    ]
    if include_pages:
        items.append(("Pages (every URL)", lambda: check_pages(user, host)))
    for fn in CUSTOM_CHECKS:
        items.append((fn.__name__.replace("check_", "").replace("_", " ").title(), fn))
    return items


def run_all(user=None, host="localhost", include_pages=True, progress=None):
    """Run every check, store the results, and return a summary dict.
    progress(step_done, total, label, result_or_None) is called before and after each check."""
    User = get_user_model()
    if user is None:
        user = User.objects.filter(is_superuser=True, is_active=True).first()
    if user is None:
        raise RuntimeError("No active superuser found - create one with: python manage.py createsuperuser")

    items = _runners(user, host, include_pages)
    results, new_bugs, auto_closed = [], 0, 0
    for idx, (label, run) in enumerate(items):
        if progress:
            progress(idx, len(items), label, None)
        _check_cancel()
        try:
            res = run()
        except RunCancelled:
            raise
        except Exception:
            res = CheckResult("System", label, "Checker crashed", "No crash")
            res.fail("crash", traceback.format_exc()[-800:], "major")
            res.finish()
        created, closed = _store(res, user)
        new_bugs += created
        auto_closed += closed
        results.append(res)
        if progress:
            progress(idx + 1, len(items), label, res)

    passed = sum(1 for r in results if r.status == "passed")
    return {
        "total": len(results), "passed": passed, "failed": len(results) - passed,
        "new_bugs": new_bugs, "auto_closed": auto_closed,
        "warnings": sum(1 for r in results for d in r.details if d[0] == "warning"),
        "results": results,
    }


# --------------------------------------------------------------------------------------
# Background run + progress (used by the dashboard button)
# State lives in a small JSON file so it also works with several server processes.
# --------------------------------------------------------------------------------------
_STATE_FILE = os.path.join(tempfile.gettempdir(), "erp_auto_tester_state.json")
_STALE_SECONDS = 20 * 60          # a "running" state older than this is treated as crashed
_thread_lock = threading.Lock()
_worker_thread = None


def _worker_alive():
    return _worker_thread is not None and _worker_thread.is_alive()


def request_stop():
    """Ask the running test to stop; if nothing is really running, just reset the state."""
    st = _read_state()
    if st.get("state") != "running":
        return False
    _write_state(cancel=True, current="Stopping...")
    return True


def force_reset():
    """Hard reset - clears a stuck 'running' state."""
    _write_state(state="stopped", finished=time.time(), cancel=False, current="Stopped", error=None)




def _read_state():
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"state": "idle"}


def _write_state(**changes):
    state = _read_state()
    state.update(changes)
    state["updated"] = time.time()
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _STATE_FILE)          # atomic: readers never see half a file
    return state


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def get_status():
    st = _read_state()
    if st.get("state") == "running":
        pid = st.get("pid")
        # Server restarted / worker died -> the run can never finish, so stop reporting "running".
        dead = (pid == os.getpid() and not _worker_alive()) or (pid != os.getpid() and pid and not _pid_alive(pid))
        if dead:
            st = _write_state(state="error", finished=time.time(),
                              error="The last run stopped unexpectedly (server restarted?).")
    if st.get("state") == "running" and time.time() - st.get("updated", 0) > _STALE_SECONDS:
        st = _write_state(state="error", error="The last run stopped unexpectedly (server restarted?).")
    if st.get("state") == "running":
        st["elapsed"] = int(time.time() - st.get("started", time.time()))
    return st


def _worker(user_id, host, include_pages):
    global _note_cb
    from django.db import close_old_connections
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)

        def note(text):
            _write_state(current=text)

        _note_cb = note

        def progress(done, total, label, res):
            if res is None:
                _write_state(step=done, total=total, current=label)
            else:
                rows = _read_state().get("results", [])
                rows.append({
                    "suite": res.suite, "title": res.title, "status": res.status, "actual": res.actual,
                    "slowest": getattr(res, "slowest", []), "slow_limit": SLOW_SECONDS,
                    "details": [
                        {"severity": sv, "item": nm, "message": str(ms)[:300]}
                        for sv, nm, ms in res.details
                    ][:100],
                })
                _write_state(step=done, total=total, results=rows)

        summary = run_all(user=user, host=host, include_pages=include_pages, progress=progress)
        _write_state(state="done", finished=time.time(), current="Finished", summary={
            k: summary[k] for k in ("total", "passed", "failed", "warnings", "new_bugs", "auto_closed")})
    except RunCancelled:
        _write_state(state="stopped", finished=time.time(), cancel=False, current="Stopped by user")
    except Exception:
        _write_state(state="error", finished=time.time(), error=traceback.format_exc()[-600:])
    finally:
        _note_cb = None
        close_old_connections()


def start_background(user, host, include_pages=True):
    """Start a run in a background thread. Returns False if one is already running."""
    with _thread_lock:
        if get_status().get("state") == "running":
            return False
        _write_state(state="running", started=time.time(), finished=None, step=0, total=0,
                     current="Starting...", results=[], summary=None, error=None,
                     cancel=False, pid=os.getpid(),
                     started_by=getattr(user, "username", ""))
        global _worker_thread
        _worker_thread = threading.Thread(target=_worker, args=(user.pk, host, include_pages), daemon=True)
        _worker_thread.start()
        return True
