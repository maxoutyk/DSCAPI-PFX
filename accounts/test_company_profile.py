from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.forms import CompanyProfileForm
from accounts.models import Tenant, TenantMembership, TenantStatus
from accounts.services import get_company_profile


class CompanyProfileFormTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme',
            slug='acme',
            status=TenantStatus.ACTIVE,
            quota_reset_at='2099-01-01T00:00:00Z',
        )
        self.profile = get_company_profile(self.tenant)

    def test_valid_profile_marks_complete(self):
        form = CompanyProfileForm(
            data={
                'company_name': 'Acme Pvt Ltd',
                'gstin': '33AAUPP8709M3ZS',
                'pan': 'AAUPP8709M',
                'address': '123 MG Road',
                'city': 'Chennai',
                'state': '33',
                'pincode': '600001',
                'primary_email': 'owner@acme.test',
                'primary_name': 'Owner',
                'primary_mobile': '9876543210',
                'secondary_email': '',
                'secondary_name': '',
                'secondary_mobile': '',
            },
            instance=self.profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertTrue(saved.is_complete)
        self.assertIsNotNone(saved.completed_at)

    def test_invalid_gstin_rejected(self):
        form = CompanyProfileForm(
            data={
                'company_name': 'Acme',
                'gstin': 'INVALID',
                'pan': 'AAUPP8709M',
                'address': 'Addr',
                'city': 'Chennai',
                'state': '33',
                'pincode': '600001',
                'primary_email': 'a@b.test',
                'primary_name': 'Owner',
                'primary_mobile': '9876543210',
                'secondary_email': '',
                'secondary_name': '',
                'secondary_mobile': '',
            },
            instance=self.profile,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('gstin', form.errors)


class CompanyProfileViewTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme',
            slug='acme',
            status=TenantStatus.ACTIVE,
            quota_reset_at='2099-01-01T00:00:00Z',
        )
        self.user = User.objects.create_user(
            username='owner@acme.test',
            email='owner@acme.test',
            password='testpass123',
        )
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role='owner', is_primary=True)

    def test_owner_can_open_profile_page(self):
        self.client.login(username='owner@acme.test', password='testpass123')
        response = self.client.get(reverse('company_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Company profile')
