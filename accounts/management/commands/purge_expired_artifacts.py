from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import PortalSignArtifact, PublicSignArtifact


class Command(BaseCommand):
    help = 'Delete expired portal and public signing artifacts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report how many rows would be deleted without deleting them.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        expired_portal = PortalSignArtifact.objects.filter(expires_at__lt=now)
        expired_public = PublicSignArtifact.objects.filter(expires_at__lt=now)
        portal_count = expired_portal.count()
        public_count = expired_public.count()

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    f'Would delete {portal_count} portal artifact(s) and {public_count} public artifact(s).',
                ),
            )
            return

        deleted_portal, _ = expired_portal.delete()
        deleted_public, _ = expired_public.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {deleted_portal} portal artifact row(s) and {deleted_public} public artifact row(s).',
            ),
        )
