from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email using the configured SMTP settings.'

    def add_arguments(self, parser):
        parser.add_argument('recipient', help='Email address to send the test message to.')

    def handle(self, *args, **options):
        if not getattr(settings, 'EMAIL_HOST', None):
            raise CommandError('EMAIL_HOST is not configured. Set SMTP variables in .env first.')

        recipient = options['recipient'].strip()
        send_mail(
            subject='IG E-Sign SMTP test',
            message=(
                'This is a test email from IG E-Sign.\n\n'
                f'EMAIL_HOST={settings.EMAIL_HOST}\n'
                f'EMAIL_PORT={settings.EMAIL_PORT}\n'
                f'DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL}\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f'Test email sent to {recipient}'))
