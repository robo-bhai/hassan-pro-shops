# Run from the project folder:
#   python manage.py shell -c "exec(open('check_security.py').read())"
#
# Read-only health check of the security module. Changes nothing.

import weakref

from django.conf import settings as dj
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse

from app.models import APIKey, IPBlacklist, SecuritySettings

problems = 0


def line(status, label, extra=""):
    global problems
    if status == "FAIL":
        problems += 1
    print(f"{status:<5} {label}" + (f"  ->  {extra}" if extra else ""))


print("--- Settings.py ---")
mw = list(dj.MIDDLEWARE)
auth_mw = "django.contrib.auth.middleware.AuthenticationMiddleware"
sec_mw = "app.middleware.SecurityMiddleware"
tfa_mw = "app.security.security_2fa.TwoFactorMiddleware"

line("PASS" if sec_mw in mw else "FAIL", "SecurityMiddleware is in MIDDLEWARE")
if sec_mw in mw and auth_mw in mw:
    line("PASS" if mw.index(sec_mw) > mw.index(auth_mw) else "FAIL", "SecurityMiddleware comes after AuthenticationMiddleware")
if tfa_mw in mw:
    line("PASS" if sec_mw in mw and mw.index(tfa_mw) > mw.index(sec_mw) else "FAIL", "TwoFactorMiddleware comes after SecurityMiddleware")
else:
    line("INFO", "TwoFactorMiddleware is not installed (login 2FA is off)")

print("\n--- Login signals ---")
def has_receiver(signal, name):
    for entry in signal.receivers:
        ref = entry[1]
        fn = ref() if isinstance(ref, weakref.ref) else ref
        if fn is not None and getattr(fn, "__name__", "") == name and fn.__module__ == "app.security.signals_security":
            return True
    return False

line("PASS" if has_receiver(user_login_failed, "record_failed_login") else "FAIL", "failed logins are recorded")
line("PASS" if has_receiver(user_logged_in, "record_successful_login") else "FAIL", "successful logins are recorded")

print("\n--- URLs ---")
for name in ["security_dashboard", "security_settings", "security_alerts", "security_logs",
             "ip_whitelist", "ip_blacklist", "api_key_management", "change_password_security",
             "two_factor_setup", "two_factor_verify"]:
    try:
        reverse(name)
        line("PASS", f"url '{name}'")
    except NoReverseMatch:
        line("FAIL", f"url '{name}' not found")
try:
    reverse("login_otp")
    line("PASS", "url 'login_otp'")
except NoReverseMatch:
    line("INFO" if tfa_mw not in mw else "FAIL", "url 'login_otp' not found")

print("\n--- Templates ---")
for tpl in ["security_base.html", "security/dashboard.html", "security/settings.html",
            "security/alerts.html", "security/logs.html", "security/api_keys.html",
            "security/ip_whitelist.html", "security/ip_blacklist.html",
            "security/change_password.html", "security/two_factor_setup.html",
            "security/two_factor_verify.html"]:
    try:
        get_template(tpl)
        line("PASS", tpl)
    except Exception as exc:
        line("FAIL", tpl, f"{type(exc).__name__}: {exc}")
try:
    get_template("security/login_otp.html")
    line("PASS", "security/login_otp.html")
except Exception:
    line("INFO" if tfa_mw not in mw else "FAIL", "security/login_otp.html missing")

print("\n--- Current security settings ---")
p = SecuritySettings.get_settings()
print(f"      failed logins before block = {p.max_login_attempts}, block duration = {p.lockout_time} min")
print(f"      session timeout = {p.session_timeout} min, auto logout = {p.enable_auto_logout}")
print(f"      2FA = {p.enable_2fa}, IP allow list = {p.enable_ip_whitelist}, IP block list = {p.enable_ip_blacklist}")
if p.session_timeout < 10:
    line("WARN", f"session timeout is only {p.session_timeout} minutes (left over from testing?)")
if p.max_login_attempts < 3:
    line("WARN", f"only {p.max_login_attempts} failed logins allowed before a block")
if p.lockout_time < 5:
    line("WARN", f"block duration is only {p.lockout_time} minutes (left over from testing?)")
if p.enable_2fa and "console" in str(dj.EMAIL_BACKEND):
    line("WARN", "2FA is on but email goes to the console, so users get no code")
if p.enable_ip_whitelist:
    from app.models import IPWhitelist
    line("WARN", f"IP allow list is on with {IPWhitelist.objects.filter(is_active=True).count()} active address(es); make sure yours is one")
if not p.enable_ip_blacklist:
    line("WARN", "IP block list is off: automatic blocks are not enforced")

print("\n--- Leftover test data ---")
active = [b.ip_address for b in IPBlacklist.objects.filter(is_active=True)]
line("PASS" if not active else "WARN", "active IP blocks", ", ".join(active) if active else "none")
from django.contrib.auth.models import User
leftovers = list(User.objects.filter(username__startswith="tfa_test_").values_list("username", flat=True))
line("PASS" if not leftovers else "WARN", "temporary test users", ", ".join(leftovers) if leftovers else "none")

print("\n--- API keys ---")
fields = {f.name for f in APIKey._meta.get_fields()}
mode = "hashed" if "key_hash" in fields else "plain text"
print(f"      APIKey storage: {mode}, rows: {APIKey.objects.count()}")

print()
print("Everything looks fine." if problems == 0 else f"{problems} problem(s) need fixing (see FAIL lines).")
