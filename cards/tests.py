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

    def test_business_card_highlight_phone(self):
        self.card.card_type = Card.TYPE_BUSINESS
        self.card.card_data.update({'extra_highlight': 'phone', 'extra_highlight_content': '880123456789'})
        self.card.save(update_fields=['card_type', 'card_data'])

        response = self.client.get(self.card.get_absolute_url())
        self.assertContains(response, 'Call us directly')
        self.assertContains(response, '+880 123456789')

    def test_business_card_highlight_skips_when_data_missing(self):
        self.card.card_type = Card.TYPE_BUSINESS
        self.card.card_data.update({'extra_highlight': 'website'})
        self.card.save(update_fields=['card_type', 'card_data'])

        response = self.client.get(self.card.get_absolute_url())
        self.assertNotContains(response, 'Visit our website')


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


class RegistrationFormTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('register')

    def _payload(self, **overrides):
        data = {
            'username': 'brandnewstudio',
            'email': 'owner@example.com',
            'password': 'StrongerPass123!',
            'phone_country': '880',
            'phone_number_local': '1782793008',
        }
        data.update(overrides)
        phone_country = data.get('phone_country', '') or ''
        phone_local = data.get('phone_number_local', '') or ''
        data['phone_number'] = f"{phone_country}{phone_local}"
        return data

    def test_username_validation_detects_existing_case_insensitive(self):
        existing = User.objects.create_user(
            username='takenname',
            email='taken@example.com',
            password='TakenPass123!'
        )
        Profile.objects.create(user=existing, phone_number='8801999111222')

        response = self.client.post(self.url, self._payload(username='TakenName', email='new@example.com'))
        self.assertEqual(response.status_code, 200)
        form = response.context['user_form']
        self.assertIn('username', form.errors)
        self.assertIn('This username is already taken.', form.errors['username'])

    def test_phone_validation_blocks_existing_number_variants(self):
        user = User.objects.create_user(username='owner', email='owner@example.com', password='OwnerPass123!')
        Profile.objects.create(user=user, phone_number='88001782793008')

        response = self.client.post(
            self.url,
            self._payload(username='duplicate', email='duplicate@example.com', phone_number_local='01782793008')
        )
        self.assertEqual(response.status_code, 200)
        form = response.context['profile_form']
        self.assertIn('phone_number_local', form.errors)
        self.assertIn('This phone number is already registered with another account.', form.errors['phone_number_local'])

    def test_phone_validation_detects_numbers_without_leading_zero_variant(self):
        user = User.objects.create_user(username='other', email='other@example.com', password='OtherPass123!')
        Profile.objects.create(user=user, phone_number='01782793008')

        response = self.client.post(
            self.url,
            self._payload(username='dup2', email='dup2@example.com', phone_number_local='1782793008')
        )
        self.assertEqual(response.status_code, 200)
        form = response.context['profile_form']
        self.assertIn('phone_number_local', form.errors)
        self.assertIn('This phone number is already registered with another account.', form.errors['phone_number_local'])

    def test_successful_registration_stores_normalized_phone(self):
        response = self.client.post(
            self.url,
            self._payload(username='freshstudio', email='fresh@example.com', phone_number_local='01799911122'),
            follow=True
        )
        self.assertEqual(response.redirect_chain[-1][0], reverse('dashboard'))
        user = User.objects.get(username='freshstudio')
        self.assertTrue(user.check_password('StrongerPass123!'))
        self.assertEqual(user.profile.phone_number, '8801799911122')


class BusinessCardCreationTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='bizowner', password='password123', email='bizowner@example.com')
        Profile.objects.create(user=self.user, phone_number='8801777000000')
        self.client.login(username='bizowner', password='password123')
        self.url = reverse('create_business_card')

    def _payload(self, **overrides):
        data = {
            'firstName': 'Biz',
            'lastName': 'Owner',
            'company': 'BizOne',
            'jobTitle': 'Director',
            'email': 'biz@company.com',
            'birthday': '',
            'phone': '8801777000000',
            'website': 'https://example.com',
            'address': '123 Market Street',
            'notes': 'Preferred contact after 10am.',
            'background_style': '#000000',
            'extra_highlight': 'email',
            'extra_highlight_content': 'hello@bizone.com',
        }
        data.update(overrides)
        return data

    def test_creates_business_card_with_highlight(self):
        response = self.client.post(self.url, self._payload(), follow=True)
        self.assertEqual(response.status_code, 200)

        card = Card.objects.get(user=self.user)
        self.assertEqual(card.card_type, Card.TYPE_BUSINESS)
        self.assertEqual(card.card_data.get('extra_highlight'), 'email')
        self.assertEqual(card.card_data.get('extra_highlight_content'), 'hello@bizone.com')

    def test_requires_highlight_content_when_selected(self):
        response = self.client.post(self.url, self._payload(extra_highlight_content=''), follow=True)
        form = response.context['form']
        self.assertIn('extra_highlight_content', form.errors)
        self.assertIn('Add the information you want to spotlight.', form.errors['extra_highlight_content'])
