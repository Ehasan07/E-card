from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Card, Profile
from urllib.parse import urlparse

class DashboardTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.profile = Profile.objects.create(user=self.user, phone_number='1234567890')
        self.card = Card.objects.create(user=self.user, card_data={'firstName': 'Test'})

        self.superuser = User.objects.create_superuser(username='super', password='password')
        self.super_profile = Profile.objects.create(user=self.superuser, phone_number='0987654321')

    def test_dashboard_unauthenticated_redirect(self):
        """Ensure unauthenticated access to /dashboard/ redirects to login."""
        response = self.client.get(reverse('dashboard'))
        self.assertIn(response.status_code, [301, 302])
        self.assertIn(reverse('login'), response.url)

    def test_dashboard_authenticated_success(self):
        """Ensure authenticated user can access dashboard and sees their card slug."""
        self.client.login(username='testuser', password='password')
        response = self.client.get(reverse('dashboard'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.card.slug)

    def test_admin_dashboard_unauthenticated_redirect(self):
        """Ensure non-superuser access to /my-admin/dashboard/ is redirected."""
        # Test with non-superuser
        self.client.login(username='testuser', password='password')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertIn(response.status_code, [301, 302])
        redirect_targets = [reverse('admin_login'), reverse('login')]
        self.assertTrue(
            any(target in response.url for target in redirect_targets),
            msg=f"Unexpected redirect target: {response.url}"
        )

    def test_admin_dashboard_superuser_success(self):
        """Ensure superuser can access admin dashboard and sees correct counts."""
        self.client.login(username='super', password='password')
        response = self.client.get(reverse('admin_dashboard'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Users')
        self.assertContains(response, '2') # 2 users created
        self.assertContains(response, 'Total Cards')
        self.assertContains(response, '1') # 1 card created
