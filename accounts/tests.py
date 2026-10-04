from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = 'test-password-123'
        cls.user = get_user_model().objects.create_user(username='taro', password=cls.password)

    def test_login_page_is_displayed(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_login_success(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'taro', 'password': self.password})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_failure(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'taro', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_redirects_to_next(self):
        response = self.client.post(
            reverse('accounts:login'), {'username': 'taro', 'password': self.password, 'next': '/admin/'}
        )
        self.assertRedirects(response, '/admin/', fetch_redirect_response=False)

    def test_authenticated_user_is_redirected(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:login'))
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_without_login(self):
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'))

    def test_field_errors_use_invalid_feedback(self):
        response = self.client.post(reverse('accounts:login'), {'username': '', 'password': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is-invalid', count=2)
        self.assertContains(response, 'invalid-feedback', count=2)

    def test_login_failure_shows_alert(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'taro', 'password': 'wrong'})
        self.assertContains(response, 'alert-danger')
        self.assertNotContains(response, 'is-invalid')
