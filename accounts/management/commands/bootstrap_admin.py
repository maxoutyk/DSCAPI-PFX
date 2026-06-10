import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create or update the Django admin superuser from environment variables.'

    def handle(self, *args, **options):
        email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
        password = os.environ.get('ADMIN_PASSWORD', '').strip()
        username = os.environ.get('ADMIN_USERNAME', email).strip().lower()

        if not email or not password:
            self.stdout.write('ADMIN_EMAIL or ADMIN_PASSWORD not set; skipping admin bootstrap.')
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True, 'is_active': True},
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        reset_password = os.environ.get('ADMIN_PASSWORD_RESET', '').lower() == 'true'
        if created or reset_password:
            user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created admin user: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Updated admin user: {username}'))
