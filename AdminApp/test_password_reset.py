from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from AdminApp.models import PasswordResetAuditEvent


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '3.228.118.5'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='sgr@sgr.test',
    PASSWORD_RESET_DOMAIN='3.228.118.5',
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='persona@sgr.test',
            password='Sgr-Initial-Password-483!',
        )
        self.reset_url = reverse('password_reset')

    def _request_reset(self, email=None, **extra):
        return self.client.post(
            self.reset_url,
            {'email': email or self.user.email},
            **extra,
        )

    def _confirm_url(self):
        return reverse(
            'password_reset_confirm',
            kwargs={
                'uidb64': urlsafe_base64_encode(force_bytes(self.user.pk)),
                'token': default_token_generator.make_token(self.user),
            },
        )

    def test_login_has_recovery_link_and_form_uses_csrf(self):
        login_response = self.client.get(reverse('login'))
        self.assertContains(login_response, '¿Olvidaste tu contraseña?')

        response = self.client.get(self.reset_url)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(self.reset_url)
        blocked = csrf_client.post(
            self.reset_url,
            {'email': self.user.email},
        )
        self.assertEqual(blocked.status_code, 403)

    def test_existing_and_unknown_email_have_same_response(self):
        existing_response = self._request_reset(HTTP_HOST='localhost')
        unknown_response = self._request_reset(
            email='desconocido@sgr.test',
            HTTP_HOST='localhost',
        )

        self.assertEqual(existing_response.status_code, 302)
        self.assertEqual(existing_response.url, unknown_response.url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Recuperación de contraseña - SGR')
        self.assertIn('http://3.228.118.5/accounts/reset/', mail.outbox[0].body)
        self.assertEqual(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.REQUEST,
            ).count(),
            2,
        )
        self.assertEqual(
            PasswordResetAuditEvent.objects.filter(
                user=self.user,
                action=PasswordResetAuditEvent.Action.REQUEST,
            ).count(),
            1,
        )
        self.assertTrue(
            PasswordResetAuditEvent.objects.filter(
                user__isnull=True,
                action=PasswordResetAuditEvent.Action.REQUEST,
            ).exists()
        )

    def test_inactive_account_does_not_receive_email(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self._request_reset()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        event = PasswordResetAuditEvent.objects.get(
            action=PasswordResetAuditEvent.Action.REQUEST,
        )
        self.assertIsNone(event.user)

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_link_is_rejected(self):
        response = self.client.get(self._confirm_url())

        self.assertContains(response, 'Este enlace ya se utilizó o venció.')
        self.assertFalse(response.context['validlink'])

    def test_link_is_single_use_and_password_change_is_audited(self):
        link = self._confirm_url()
        first_response = self.client.get(link)
        self.assertEqual(first_response.status_code, 302)
        form_url = first_response.url
        self.client.get(form_url)

        response = self.client.post(form_url, {
            'new_password1': 'Sgr-Changed-Password-572!',
            'new_password2': 'Sgr-Changed-Password-572!',
        })

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Sgr-Changed-Password-572!'))
        self.assertContains(self.client.get(link), 'Este enlace ya se utilizó o venció.')
        event = PasswordResetAuditEvent.objects.get(
            action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
        )
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.ip_address, '127.0.0.1')

    def test_weak_password_is_rejected_by_configured_validators(self):
        link_response = self.client.get(self._confirm_url())
        form_url = link_response.url
        self.client.get(form_url)

        response = self.client.post(form_url, {
            'new_password1': 'password',
            'new_password2': 'password',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Sgr-Initial-Password-483!'))
        self.assertFalse(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
            ).exists()
        )

    def test_requests_are_limited_to_five_per_hour_by_ip_and_email(self):
        responses = [
            self._request_reset(REMOTE_ADDR=f'203.0.113.{index + 1}')
            for index in range(6)
        ]

        self.assertTrue(all(response.status_code == 302 for response in responses))
        self.assertEqual(len(mail.outbox), 5)
        self.assertTrue(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.REQUEST,
                was_rate_limited=True,
            ).exists()
        )

    def test_request_limit_also_applies_to_multiple_emails_from_one_ip(self):
        responses = [
            self._request_reset(
                email=f'persona-{index}@sgr.test',
                REMOTE_ADDR='203.0.113.55',
            )
            for index in range(6)
        ]

        self.assertTrue(all(response.status_code == 302 for response in responses))
        self.assertTrue(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.REQUEST,
                was_rate_limited=True,
                ip_address='203.0.113.55',
            ).exists()
        )
