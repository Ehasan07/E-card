import os
import django
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecard_project.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from cards.models import Card, Profile
from django.db import connection

def run_tests():
    # Manually create a test database
    db_name = connection.creation.create_test_db()

    client = Client()
    superuser = User.objects.create_superuser(
        username='admin_test', 
        password='Pass12345!',
        email='admin@test.com'
    )
    Profile.objects.create(user=superuser, phone_number='123456789')
    Card.objects.create(user=superuser, card_data={'firstName': 'Admin', 'lastName': 'Test'})

    print("\n--- Testing /dashboard/ (unauthenticated) ---")
    response = client.get(reverse('dashboard'))
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 302, "Should redirect to login"

    print("\n--- Testing /dashboard/ (authenticated) ---")
    client.login(username='admin_test', password='Pass12345!')
    try:
        response = client.get(reverse('dashboard'))
        print(f"Status Code: {response.status_code}")
        if response.status_code == 500:
            print("Error found as expected.")
            # In a real test, we'd parse the content, but for CLI, we'll just note the error
            # and print the traceback from the exception handler.
    except Exception as e:
        print(f"Caught exception: {e}")
        traceback.print_exc()

    print("\n--- Testing /my-admin/dashboard/ (unauthenticated) ---")
    client.logout()
    response = client.get(reverse('admin_dashboard'))
    print(f"Status Code: {response.status_code}")
    assert response.status_code in [302, 403], "Should redirect or be forbidden"

    print("\n--- Testing /my-admin/dashboard/ (authenticated) ---")
    client.login(username='admin_test', password='Pass12345!')
    try:
        response = client.get(reverse('admin_dashboard'))
        print(f"Status Code: {response.status_code}")
        if response.status_code == 500:
            print("Error found as expected.")
    except Exception as e:
        print(f"Caught exception: {e}")
        traceback.print_exc()

    # Clean up the test database
    connection.creation.destroy_test_db(db_name)

if __name__ == "__main__":
    run_tests()

