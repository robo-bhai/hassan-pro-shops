from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Test email bhejta hai:  python manage.py send_test_email apni@email.com'

    def add_arguments(self, parser):
        parser.add_argument('to')

    def handle(self, *args, **options):
        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Sender : {getattr(settings, "BREVO_SENDER_NAME", "")} <{settings.DEFAULT_FROM_EMAIL}>')
        sent = send_mail('Test email', 'Email chal gayi!', settings.DEFAULT_FROM_EMAIL,
                         [options['to']], html_message='<b>Email chal gayi!</b>', fail_silently=False)
        self.stdout.write(self.style.SUCCESS('Email bhej di gayi.') if sent else self.style.ERROR('Email nahi gayi.'))
