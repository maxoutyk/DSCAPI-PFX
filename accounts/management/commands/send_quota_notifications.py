from django.core.management.base import BaseCommand

from accounts.quota_notifications import process_scheduled_quota_notifications


class Command(BaseCommand):
    help = (
        'Email tenant owners about expiring entitlements and low remaining quota. '
        'Schedule daily, e.g. cron: 0 9 * * * python manage.py send_quota_notifications'
    )

    def handle(self, *args, **options):
        result = process_scheduled_quota_notifications()
        if result.get('skipped'):
            self.stdout.write(self.style.WARNING('Quota notifications are disabled or SMTP is not configured.'))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {result['expiry_reminders']} expiry reminder(s) and "
                f"{result['low_quota']} low-quota alert(s).",
            ),
        )
