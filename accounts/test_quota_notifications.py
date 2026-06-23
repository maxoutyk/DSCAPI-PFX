from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import MembershipRole, QuotaEntitlementStatus, QuotaPlan, Tenant, TenantMembership, TenantStatus
from accounts.quota import grant_entitlement, renew_entitlement
from accounts.quota_notifications import (
    send_expiry_reminder_email,
    send_low_quota_email,
)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST='smtp.test.local',
    SITE_URL='http://testserver',
    QUOTA_NOTIFICATIONS_ENABLED=True,
    QUOTA_EXPIRY_REMINDER_DAYS=30,
    QUOTA_LOW_REMAINING_PERCENT=10,
)
class QuotaNotificationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            password='pass',
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name='Notify Org',
            slug='notify-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )

    def test_grant_entitlement_emails_owner(self):
        with self.captureOnCommitCallbacks(execute=True):
            grant_entitlement(
                self.tenant,
                plan=QuotaPlan.PRO,
                purchased_limit=10_000,
                duration_months=12,
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('owner@example.com', mail.outbox[0].to)
        self.assertIn('Pro', mail.outbox[0].subject)

    def test_renew_entitlement_emails_owner(self):
        with self.captureOnCommitCallbacks(execute=True):
            grant_entitlement(
                self.tenant,
                plan=QuotaPlan.PRO,
                purchased_limit=10_000,
                duration_months=12,
            )
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            renew_entitlement(
                self.tenant,
                plan=QuotaPlan.PRO_PLUS,
                purchased_limit=15_000,
                duration_months=12,
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('renewed', mail.outbox[0].subject.lower())

    def test_expiry_reminder_sent_once(self):
        from django.utils import timezone

        from accounts.models import QuotaEntitlement

        entitlement = QuotaEntitlement.objects.create(
            tenant=self.tenant,
            plan_at_grant=QuotaPlan.PRO,
            purchased_limit=10_000,
            carry_forward=0,
            quota_limit=10_000,
            usage_count=0,
            starts_at=timezone.now() - timedelta(days=335),
            ends_at=timezone.now() + timedelta(days=20),
            status=QuotaEntitlementStatus.ACTIVE,
        )
        self.assertTrue(send_expiry_reminder_email(entitlement))
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()
        entitlement.refresh_from_db()
        self.assertFalse(send_expiry_reminder_email(entitlement))
        self.assertEqual(len(mail.outbox), 0)

    def test_low_quota_alert_when_below_threshold(self):
        from django.utils import timezone

        from accounts.models import QuotaEntitlement

        entitlement = QuotaEntitlement.objects.create(
            tenant=self.tenant,
            plan_at_grant=QuotaPlan.PRO,
            purchased_limit=10_000,
            carry_forward=0,
            quota_limit=10_000,
            usage_count=9_950,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=200),
            status=QuotaEntitlementStatus.ACTIVE,
        )
        self.assertTrue(send_low_quota_email(entitlement))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Low quota', mail.outbox[0].subject)

    def test_scheduled_command_sends_reminders(self):
        from django.core.management import call_command
        from django.utils import timezone

        from accounts.models import QuotaEntitlement

        QuotaEntitlement.objects.create(
            tenant=self.tenant,
            plan_at_grant=QuotaPlan.PRO,
            purchased_limit=1_000,
            carry_forward=0,
            quota_limit=1_000,
            usage_count=995,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=10),
            status=QuotaEntitlementStatus.ACTIVE,
        )
        call_command('send_quota_notifications')
        subjects = [message.subject for message in mail.outbox]
        self.assertTrue(any('expiring' in subject.lower() or 'expires' in subject.lower() for subject in subjects))
        self.assertTrue(any('quota' in subject.lower() for subject in subjects))

    @override_settings(QUOTA_NOTIFICATIONS_ENABLED=False)
    def test_disabled_notifications_skip_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            grant_entitlement(
                self.tenant,
                plan=QuotaPlan.PRO,
                purchased_limit=10_000,
                duration_months=12,
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_multiple_owners_all_receive_email(self):
        member_owner = User.objects.create_user(
            username='coowner@example.com',
            email='coowner@example.com',
            password='pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=member_owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=False,
        )
        with self.captureOnCommitCallbacks(execute=True):
            grant_entitlement(
                self.tenant,
                plan=QuotaPlan.PRO,
                purchased_limit=10_000,
                duration_months=12,
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            set(mail.outbox[0].to),
            {'owner@example.com', 'coowner@example.com'},
        )
