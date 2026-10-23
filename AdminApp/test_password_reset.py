import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import (
    PasswordResetAuditEvent,
    PasswordResetCode,
)


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
        self.request_url = reverse('password_reset')
        self.code_url = reverse('password_reset_code')
        self.new_password_url = reverse('password_reset_new')

    def _request_reset(self, email=None, client=None, **extra):
        client = client or self.client
        return client.post(
            self.request_url,
            {'email': email or self.user.email},
            **extra,
        )

    def _request_code(self, client=None):
        response = self._request_reset(client=client, HTTP_HOST='localhost')
        self.assertRedirects(response, self.code_url)
        self.assertEqual(len(mail.outbox), 1)
        code_match = re.search(r'(\d{6})', mail.outbox[0].body)
        self.assertIsNotNone(code_match)
        return code_match.group(1)

    def _verify_code(self, code, client=None):
        client = client or self.client
        return client.post(
            self.code_url,
            {'action': 'verify', 'code': code},
            HTTP_HOST='localhost',
        )

    def test_login_has_recovery_link_csrf_and_rejects_inactive_accounts(self):
        login_response = self.client.get(reverse('login'))
        self.assertContains(login_response, '¿Olvidaste tu contraseña?')
        self.assertContains(login_response, 'Correo electrónico')

        response = self.client.get(self.request_url)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(self.request_url)
        blocked = csrf_client.post(
            self.request_url,
            {'email': self.user.email},
        )
        self.assertEqual(blocked.status_code, 403)

        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        login_response = self.client.post(reverse('login'), {
            'username': self.user.email,
            'password': 'Sgr-Initial-Password-483!',
        })
        self.assertEqual(login_response.status_code, 200)
        self.assertFalse(login_response.wsgi_request.user.is_authenticated)

    def test_existing_and_unknown_email_have_same_response(self):
        existing_client = Client()
        unknown_client = Client()
        existing_response = self._request_reset(
            client=existing_client,
            HTTP_HOST='localhost',
        )
        unknown_response = self._request_reset(
            email='desconocido@sgr.test',
            client=unknown_client,
            HTTP_HOST='localhost',
        )

        self.assertEqual(existing_response.status_code, 302)
        self.assertEqual(existing_response.url, unknown_response.url)
        self.assertContains(
            existing_client.get(existing_response.url),
            'Si existe una cuenta activa con ese correo',
        )
        self.assertContains(
            unknown_client.get(unknown_response.url),
            'Si existe una cuenta activa con ese correo',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'Código de recuperación de contraseña - SGR',
        )
        self.assertRegex(mail.outbox[0].body, r'\b\d{6}\b')
        self.assertNotIn('/accounts/reset/', mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        html_body, content_type = mail.outbox[0].alternatives[0]
        self.assertEqual(content_type, 'text/html')
        code = re.search(r'(\d{6})', mail.outbox[0].body).group(1)
        minutes = (600 + 59) // 60
        self.assertIn(code, html_body)
        self.assertIn(f'{minutes} minutos', html_body)
        self.assertIn('cid:logo_serena', html_body)
        self.assertNotRegex(html_body, r'<a\b|href\s*=')
        self.assertNotIn(code, mail.outbox[0].subject)
        logo_attachments = [
            attachment
            for attachment in mail.outbox[0].attachments
            if not isinstance(attachment, tuple)
        ]
        self.assertTrue(
            any(
                attachment['Content-ID'] == '<logo_serena>'
                for attachment in logo_attachments
            )
        )
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

    def test_inactive_account_does_not_receive_code(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self._request_reset(HTTP_HOST='localhost')

        self.assertRedirects(response, self.code_url)
        self.assertEqual(len(mail.outbox), 0)
        event = PasswordResetAuditEvent.objects.get(
            action=PasswordResetAuditEvent.Action.REQUEST,
        )
        self.assertIsNone(event.user)

    def test_code_is_hashed_and_must_be_verified_before_new_password(self):
        code = self._request_code()
        record = PasswordResetCode.objects.get(user=self.user)
        self.assertNotEqual(record.code_hash, code)
        self.assertTrue(check_password(code, record.code_hash))

        bypass = self.client.get(self.new_password_url)
        self.assertRedirects(bypass, self.code_url)

        response = self._verify_code(code)
        self.assertRedirects(response, self.new_password_url)
        self.assertIsNotNone(
            PasswordResetAuditEvent.objects.filter(
                user=self.user,
                action=PasswordResetAuditEvent.Action.CODE_VALIDATION,
            ).first()
        )
        self.assertContains(self.client.get(self.new_password_url), 'PASO 3 DE 3')

    def test_malformed_and_incorrect_codes_are_audited_and_limited(self):
        code = self._request_code()

        malformed_response = self._verify_code('12')
        self.assertEqual(malformed_response.status_code, 200)
        self.assertEqual(
            PasswordResetCode.objects.get(user=self.user).failed_attempts,
            1,
        )
        wrong_response = self._verify_code('000000' if code != '000000' else '000001')
        self.assertEqual(wrong_response.status_code, 200)
        self.assertEqual(
            PasswordResetCode.objects.get(user=self.user).failed_attempts,
            2,
        )
        self.assertEqual(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.CODE_VALIDATION,
            ).count(),
            2,
        )

    @override_settings(PASSWORD_RESET_CODE_MAX_ATTEMPTS=2)
    def test_attempt_limit_blocks_a_correct_code_after_two_failures(self):
        code = self._request_code()
        self._verify_code('000000' if code != '000000' else '000001')
        self._verify_code('000000' if code != '000000' else '000001')

        response = self._verify_code(code)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PasswordResetCode.objects.get(user=self.user).failed_attempts,
            2,
        )
        self.assertTrue(
            PasswordResetAuditEvent.objects.filter(
                action=PasswordResetAuditEvent.Action.CODE_VALIDATION,
                was_rate_limited=True,
            ).exists()
        )

    def test_expired_code_is_rejected(self):
        code = self._request_code()
        record = PasswordResetCode.objects.get(user=self.user)
        record.expires_at = timezone.now() - timedelta(seconds=1)
        record.save(update_fields=['expires_at'])

        response = self._verify_code(code)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            PasswordResetCode.objects.get(user=self.user).verified_at
        )

    def test_resend_waits_for_cooldown_and_rotates_code(self):
        first_code = self._request_code()
        first_record = PasswordResetCode.objects.get(user=self.user)
        first_sent_at = first_record.last_sent_at

        limited_response = self.client.post(
            self.code_url,
            {'action': 'resend'},
            HTTP_HOST='localhost',
        )
        self.assertRedirects(limited_response, self.code_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            PasswordResetCode.objects.get(user=self.user).last_sent_at,
            first_sent_at,
        )

        next_code_value = (int(first_code) + 1) % 1_000_000
        with (
            patch(
                'config.password_reset.timezone.now',
                return_value=first_sent_at + timedelta(seconds=46),
            ),
            patch(
                'config.password_reset.secrets.randbelow',
                return_value=next_code_value,
            ),
        ):
            resent_response = self.client.post(
                self.code_url,
                {'action': 'resend'},
                HTTP_HOST='localhost',
            )
        self.assertRedirects(resent_response, self.code_url)
        self.assertEqual(len(mail.outbox), 2)
        second_code = re.search(r'(\d{6})', mail.outbox[1].body).group(1)
        self.assertNotEqual(first_code, second_code)
        self.assertNotEqual(
            PasswordResetCode.objects.get(user=self.user).last_sent_at,
            first_sent_at,
        )
        self.assertEqual(self._verify_code(first_code).status_code, 200)

    def test_verified_code_changes_password_once_and_records_audit(self):
        code = self._request_code()
        self.assertRedirects(
            self._verify_code(code),
            self.new_password_url,
        )

        response = self.client.post(self.new_password_url, {
            'new_password1': 'Sgr-Changed-Password-572!',
            'new_password2': 'Sgr-Changed-Password-572!',
        })

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Sgr-Changed-Password-572!'))
        self.assertFalse(self.user.check_password('Sgr-Initial-Password-483!'))
        self.assertIsNotNone(
            PasswordResetCode.objects.get(user=self.user).used_at
        )
        self.assertTrue(
            PasswordResetAuditEvent.objects.filter(
                user=self.user,
                action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
                ip_address='127.0.0.1',
            ).exists()
        )
        self.assertEqual(self._verify_code(code).status_code, 302)

    def test_weak_password_is_rejected_by_configured_validators(self):
        code = self._request_code()
        self._verify_code(code)

        response = self.client.post(self.new_password_url, {
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

    def test_legacy_reset_link_only_redirects_to_code_request(self):
        response = self.client.get(reverse(
            'password_reset_confirm',
            kwargs={'uidb64': 'legacy', 'token': 'legacy'},
        ))

        self.assertRedirects(response, self.request_url)
        self.assertEqual(len(mail.outbox), 0)
