from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify
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
