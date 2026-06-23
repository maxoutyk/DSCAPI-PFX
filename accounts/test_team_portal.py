from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts.models import MembershipRole, Tenant, TenantMembership, TenantStatus


class TeamPortalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            password='owner-pass',
            is_active=True,
        )
        self.member = User.objects.create_user(
            username='member@example.com',
            email='member@example.com',
            password='member-pass',
            is_active=True,
        )
        self.tenant = Tenant.objects.create(
            name='Team Org',
            slug='team-org',
            status=TenantStatus.ACTIVE,
            monthly_quota=100,
        )
        self.owner_membership = TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
            is_primary=True,
        )
        self.member_membership = TenantMembership.objects.create(
            user=self.member,
            tenant=self.tenant,
            role=MembershipRole.MEMBER,
            is_primary=True,
        )
        self.client = Client()

    def test_owner_can_open_team_page(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.get('/dashboard/team/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'member@example.com')
        self.assertContains(response, 'Owner')

    def test_member_cannot_open_team_page(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/team/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_owner_can_remove_member(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post(
            '/dashboard/team/',
            {'remove_member': str(self.member_membership.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TenantMembership.objects.filter(pk=self.member_membership.pk).exists(),
        )

    def test_owner_cannot_remove_self_when_sole_owner(self):
        self.client.login(username='owner@example.com', password='owner-pass')
        response = self.client.post(
            '/dashboard/team/',
            {'remove_member': str(self.owner_membership.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TenantMembership.objects.filter(pk=self.owner_membership.pk).exists(),
        )

    def test_member_can_open_dashboard_and_sign_pages(self):
        self.client.login(username='member@example.com', password='member-pass')
        self.assertEqual(self.client.get('/dashboard/').status_code, 200)
        self.assertEqual(self.client.get('/dashboard/sign/').status_code, 200)
        self.assertEqual(self.client.get('/dashboard/sign/usb/').status_code, 200)

    def test_member_cannot_open_usage_report(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/usage/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_member_cannot_open_company_profile(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_member_cannot_open_gst_portal(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/gst/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_member_can_view_signature_styles_read_only(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/signature/')
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_create_signature_style(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/signature/new/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/')

    def test_member_dashboard_shows_usage_snippet(self):
        self.client.login(username='member@example.com', password='member-pass')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Organization usage this month')
        self.assertNotContains(response, 'Manage keys')
