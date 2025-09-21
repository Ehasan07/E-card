from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from unittest.mock import patch
from django.core import mail

from .models import Card, Profile

class CardModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.profile = Profile.objects.create(user=self.user, phone_number='1234567890')

    def test_card_creation_and_slugification(self):
        """Test that a card is created with a slug equal to the username."""
        card = Card.objects.create(user=self.user, card_data={'firstName': 'Test', 'lastName': 'User'})
        self.assertEqual(card.slug, slugify(self.user.username))
        self.assertTrue(card.is_active)

    def test_get_absolute_url(self):
        """Test the get_absolute_url method returns the correct URL."""
        card = Card.objects.create(user=self.user, card_data={})
        expected_url = reverse('view_card', kwargs={'slug': card.slug})
        self.assertEqual(card.get_absolute_url(), expected_url)

class CardViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.profile = Profile.objects.create(user=self.user, phone_number='1234567890')
        self.client.login(username='testuser', password='password')
        self.card = Card.objects.create(user=self.user, card_data={'firstName': 'Test'})

    def test_view_card_uses_slug(self):
        """Test that the card detail view is accessible via its slug."""
        response = self.client.get(reverse('view_card', kwargs={'slug': self.card.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.card.card_data['firstName'])

    def test_create_card_redirects_if_card_exists(self):
        """Test that accessing the create page redirects to the edit page if a card already exists."""
        response = self.client.get(reverse('create_card'))
        self.assertRedirects(response, reverse('edit_card', kwargs={'slug': self.card.slug}))

    def test_card_detail_view_context(self):
        """Test that the card detail view has the correct context for owner and visitor."""
        # Test as owner
        response = self.client.get(self.card.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_owner'])
        self.assertFalse(response.context['from_qr'])
        self.assertFalse(response.context['show_guest_cta'])
        self.assertNotContains(response, 'Create a card for yourself')

        # Test as owner from QR
        response = self.client.get(self.card.get_absolute_url() + '?qr=1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_owner'])
        self.assertTrue(response.context['from_qr'])

        # Test as visitor (logged out)
        self.client.logout()
        response = self.client.get(self.card.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_owner'])
        self.assertFalse(response.context['from_qr'])
        self.assertTrue(response.context['show_guest_cta'])
        self.assertContains(response, 'Create a card for yourself')


class PasswordResetOtpTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='resetuser', password='password123', email='reset@example.com')
        self.profile = Profile.objects.create(user=self.user, phone_number='9999999999')

    def _request_otp(self, otp_value='123456'):
        mail.outbox.clear()
        with patch('cards.views.random.randint', return_value=int(otp_value)):
            response = self.client.post(reverse('password_reset_request_otp'), {'email': self.user.email}, follow=True)
        self.profile.refresh_from_db()
        return response

    def test_request_otp_hashes_and_sets_expiry(self):
        response = self._request_otp('654321')
        self.assertEqual(response.redirect_chain[-1][0], reverse('password_reset_verify_otp'))
        self.assertIsNotNone(self.profile.otp)
        self.assertNotEqual(self.profile.otp, '654321')
        self.assertIsNotNone(self.profile.otp_expires_at)
        self.assertGreater(self.profile.otp_expires_at, timezone.now())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'dss@dupno.com')

    def test_rate_limit_blocks_immediate_second_request(self):
        first = self._request_otp('111111')
        self.assertEqual(first.redirect_chain[-1][0], reverse('password_reset_verify_otp'))
        second_response = self.client.post(reverse('password_reset_request_otp'), {'email': self.user.email})
        self.assertEqual(second_response.status_code, 200)
        form = second_response.context['form']
        self.assertEqual(form.errors.get('email')[0][:12], 'Please wait ')
        # ensure no additional email dispatched
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_otp_success_sets_session_flag(self):
        self._request_otp('222333')
        response = self.client.post(reverse('password_reset_verify_otp'), {'otp': '222333'})
        self.assertRedirects(response, reverse('password_reset_set_new'))
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.otp)
        session = self.client.session
        self.assertTrue(session.get('password_reset_verified'))

    def test_complete_password_reset_updates_credentials(self):
        self._request_otp('777888')
        self.client.post(reverse('password_reset_verify_otp'), {'otp': '777888'})
        response = self.client.post(
            reverse('password_reset_set_new'),
            {
                'new_password1': 'NewSecurePass123!',
                'new_password2': 'NewSecurePass123!',
            }
        )
        self.assertRedirects(response, reverse('login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecurePass123!'))
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.otp_requested_at)
