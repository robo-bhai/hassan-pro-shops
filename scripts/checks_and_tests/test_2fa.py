# Run from the project folder:
#   python manage.py shell -c "exec(open('test_2fa.py').read())"
#
# Tests the login 2FA end to end with temporary users and an in-memory email
# outbox. Nothing is sent. The temporary users are deleted at the end and the
# 2FA setting is put back as it was.

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

from app.models import OTPVerification, SecuritySettings

results = []


def check(label, ok):
    results.append(ok)
    print(("PASS" if ok else "FAIL"), "-", label)


def goes_to_otp(response):
    return response.status_code == 302 and "login-otp" in response["Location"]


def new_client(user):
    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(user)
    return client


policy = SecuritySettings.get_settings()
original_2fa = policy.enable_2fa
users = []

try:
    staff = User.objects.create_user("tfa_test_staff", "tfa_test@example.com", "Test@12345", is_staff=True)
    normal = User.objects.create_user("tfa_test_normal", "tfa_normal@example.com", "Test@12345")
    no_email = User.objects.create_user("tfa_test_noemail", "", "Test@12345", is_staff=True)
    users = [staff, normal, no_email]

    otp_url = reverse("login_otp")

    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ALLOWED_HOSTS=["*"],
    ):
        mail.outbox = []

        # 2FA off: nobody is challenged
        policy.enable_2fa = False
        policy.save()
        check("2FA off: staff is not challenged", not goes_to_otp(new_client(staff).get("/")))

        # 2FA on
        policy.enable_2fa = True
        policy.save()

        check("non-staff user is not challenged", not goes_to_otp(new_client(normal).get("/")))
        check("staff without email is not challenged", not goes_to_otp(new_client(no_email).get("/")))

        client = new_client(staff)
        response = client.get("/")
        check("staff is sent to the code page", goes_to_otp(response))

        response = client.get(otp_url)
        check("code page opens", response.status_code == 200)
        check("exactly one email was sent", len(mail.outbox) == 1)

        otp = OTPVerification.objects.filter(user=staff, otp_type="login").order_by("-pk").first()
        check("email contains the code", bool(otp) and otp.otp_code in mail.outbox[0].body)

        wrong = "000000" if otp.otp_code != "000000" else "111111"
        response = client.post(otp_url, {"otp_code": wrong})
        check("wrong code is rejected", response.status_code == 302 and "login-otp" in response["Location"])
        check("still blocked after a wrong code", goes_to_otp(client.get("/")))

        response = client.post(otp_url, {"otp_code": otp.otp_code})
        check("correct code is accepted", response.status_code == 302 and "login-otp" not in response["Location"])
        check("staff can use the site after verifying", not goes_to_otp(client.get("/")))

        # a used code cannot be reused in another session
        other = new_client(staff)
        other.get("/")
        other.get(otp_url)
        response = other.post(otp_url, {"otp_code": otp.otp_code})
        check("used code is rejected in a new session", goes_to_otp(other.get("/")))

        # resend cooldown
        before = len(mail.outbox)
        client2 = new_client(staff)
        client2.get("/")
        client2.get(otp_url)
        client2.post(otp_url, {"action": "resend"})
        check("resend within 60 seconds sends no extra email", len(mail.outbox) == before + 1)

        # lock after too many wrong codes
        cache.delete(f"otp_failures:{staff.pk}:login")
        client3 = new_client(staff)
        client3.get("/")
        client3.get(otp_url)
        latest = OTPVerification.objects.filter(user=staff, otp_type="login").order_by("-pk").first()
        bad = "000000" if latest.otp_code != "000000" else "111111"
        for _ in range(5):
            client3.post(otp_url, {"otp_code": bad})
        client3.post(otp_url, {"otp_code": latest.otp_code})
        check("5 wrong codes lock out even the correct code", goes_to_otp(client3.get("/")))

finally:
    policy.enable_2fa = original_2fa
    policy.save()
    for user in users:
        cache.delete(f"otp_failures:{user.pk}:login")
        user.delete()

print()
print(f"{sum(results)} of {len(results)} checks passed")
