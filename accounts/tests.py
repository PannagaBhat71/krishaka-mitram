from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_view_get(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/signup.html')

    def test_signup_view_post_success(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newfarmer',
            'email': 'farmer@example.com',
            'role': 'farmer',
            'password': 'SecurePassword123!',
            'password_confirmation': 'SecurePassword123!',
            'password1': 'SecurePassword123!',
            'password2': 'SecurePassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newfarmer').exists())
        user = User.objects.get(username='newfarmer')
        self.assertEqual(user.role, 'farmer')

    def test_login_and_logout(self):
        user = User.objects.create_user(username='testbuyer', password='Password123!', role='buyer')
        
        # Test GET login
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

        # Test POST login
        login_resp = self.client.post(reverse('login'), {
            'username': 'testbuyer',
            'password': 'Password123!',
        })
        self.assertEqual(login_resp.status_code, 302)

        # Test Logout
        logout_resp = self.client.get(reverse('logout'))
        self.assertEqual(logout_resp.status_code, 302)
