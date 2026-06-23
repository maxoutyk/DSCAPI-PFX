from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.invites import InviteError, accept_tenant_invite, create_tenant_invite, list_pending_invites
from accounts.models import MembershipRole, Tenant, TenantInvite, TenantMembership, TenantStatus


@override_settings(
    TEAMS_ENABLED=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='http://testserver',
)
class TeamInviteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        self.other_owner = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='other-pass',
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name='Team Org',
            slug='team-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        self.other_tenant = Tenant.objects.create(
            name='Other Org',
            slug='other-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        TenantMembership.objects.create(
            user=self.other_owner,
            tenant=self.other_tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        self.client = Client()

    def test_owner_can_send_invite(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post(
            '/dashboard/team/',
            {'send_invite': '1', 'email': 'member@example.com'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TenantInvite.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/invite/', mail.outbox[0].body)

    def test_invite_accept_creates_membership_not_tenant(self):
        invite = create_tenant_invite(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
        )
        tenant_count = Tenant.objects.count()
        response = self.client.post(f'/invite/{invite.token}/', {
            'action': 'register',
            'email': 'member@example.com',
            'password': 'member-pass1',
            'password_confirm': 'member-pass1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tenant.objects.count(), tenant_count)
        member = User.objects.get(email='member@example.com')
        membership = TenantMembership.objects.get(user=member, tenant=self.tenant)
        self.assertEqual(membership.role, MembershipRole.MEMBER)

    def test_invite_rejects_existing_owner_of_another_org(self):
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='other@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.client.login(username='other@example.com', password='other-pass')
        response = self.client.post(f'/invite/{invite.token}/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TenantMembership.objects.filter(user=self.other_owner, tenant=self.tenant).exists(),
        )

    def test_create_invite_rejects_email_that_owns_another_org(self):
        with self.assertRaises(InviteError):
            create_tenant_invite(
                tenant=self.tenant,
                email='other@example.com',
                invited_by=self.owner,
            )

    def test_expired_invite_shows_unavailable_page(self):
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.get(f'/invite/{invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'expired')

    @override_settings(TEAMS_ENABLED=False)
    def test_accept_url_blocked_when_teams_disabled(self):
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.get(f'/invite/{invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not enabled')

    def test_accept_is_idempotent_for_existing_member(self):
        member = User.objects.create_user(
            username='member@example.com',
            email='member@example.com',
            password='member-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=member,
            tenant=self.tenant,
            role=MembershipRole.MEMBER,
            is_primary=True,
        )
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
            accepted_at=timezone.now(),
        )
        tenant = accept_tenant_invite(invite=invite, user=member)
        self.assertEqual(tenant.pk, self.tenant.pk)

    def test_member_cannot_send_invite(self):
        member = User.objects.create_user(
            username='member@example.com',
            email='member@example.com',
            password='member-pass',
            is_active=True,
        )
        TenantMembership.objects.create(
            user=member,
            tenant=self.tenant,
            role=MembershipRole.MEMBER,
            is_primary=True,
        )
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.post(
            '/dashboard/team/',
            {'send_invite': '1', 'email': 'new@example.com'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')
        self.assertEqual(TenantInvite.objects.count(), 0)

    @patch('accounts.views.is_rate_limited', return_value=True)
    def test_team_invite_rate_limited(self, _mock):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post(
            '/dashboard/team/',
            {'send_invite': '1', 'email': 'member@example.com'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TenantInvite.objects.count(), 0)

    def test_owner_can_resend_pending_invite(self):
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        old_token = invite.token
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post('/dashboard/team/', {'resend_invite': str(invite.pk)})
        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertNotEqual(invite.token, old_token)
        self.assertEqual(len(mail.outbox), 1)

    def test_owner_can_revoke_pending_invite(self):
        invite = TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post('/dashboard/team/', {'revoke_invite': str(invite.pk)})
        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.revoked_at)

    def test_revoked_invite_not_listed_as_pending(self):
        TenantInvite.objects.create(
            tenant=self.tenant,
            email='member@example.com',
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
            revoked_at=timezone.now(),
        )
        self.assertEqual(list_pending_invites(self.tenant).count(), 0)
