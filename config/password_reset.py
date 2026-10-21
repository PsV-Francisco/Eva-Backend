import hashlib
import hmac
import ipaddress
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.views import (
    PasswordResetConfirmView as DjangoPasswordResetConfirmView,
    PasswordResetView as DjangoPasswordResetView,
)
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone

from AdminApp.models import PasswordResetAuditEvent, PasswordResetRateLimitKey

logger = logging.getLogger(__name__)


class SolicitudRecuperacionForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].label = 'Correo electrónico'
        self.fields['email'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'email',
            'autofocus': True,
        })


class NuevaContrasenaForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = 'Nueva contraseña'
        self.fields['new_password2'].label = 'Confirmar nueva contraseña'
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'new-password',
            })


def _fingerprint(value):
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        value.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def _request_ip(request):
    remote_addr = request.META.get('REMOTE_ADDR', '')
    if not remote_addr:
        return None
    try:
        return str(ipaddress.ip_address(remote_addr))
    except ValueError:
        logger.warning('REMOTE_ADDR inválida al solicitar recuperación de contraseña.')
        return None


def _record_reset_request(request, email):
    email_fingerprint = _fingerprint(f'email:{email.strip().casefold()}')
    ip_address = _request_ip(request)
    lock_keys = [_fingerprint(f'email:{email_fingerprint}')]
    if ip_address:
        lock_keys.append(_fingerprint(f'ip:{ip_address}'))

    now = timezone.now()
    recent_requests = PasswordResetAuditEvent.objects.filter(
        action=PasswordResetAuditEvent.Action.REQUEST,
        created_at__gte=now - timedelta(
            seconds=settings.PASSWORD_RESET_RATE_WINDOW
        ),
    )
    user = get_user_model()._default_manager.filter(
        email__iexact=email,
        is_active=True,
    ).first()

    with transaction.atomic():
        PasswordResetRateLimitKey.objects.bulk_create(
            [PasswordResetRateLimitKey(key=key) for key in lock_keys],
            ignore_conflicts=True,
        )
        list(
            PasswordResetRateLimitKey.objects.select_for_update()
            .filter(key__in=lock_keys)
            .order_by('key')
        )
        limited_by_email = recent_requests.filter(
            email_fingerprint=email_fingerprint,
        ).count() >= settings.PASSWORD_RESET_RATE_LIMIT
        limited_by_ip = bool(
            ip_address
            and recent_requests.filter(ip_address=ip_address).count()
            >= settings.PASSWORD_RESET_RATE_LIMIT
        )
        limited = limited_by_email or limited_by_ip
        PasswordResetAuditEvent.objects.create(
            user=user,
            action=PasswordResetAuditEvent.Action.REQUEST,
            email_fingerprint=email_fingerprint,
            ip_address=ip_address,
            was_rate_limited=limited,
        )
    return limited


class PasswordResetView(DjangoPasswordResetView):
    def form_valid(self, form):
        if _record_reset_request(
            self.request,
            form.cleaned_data['email'],
        ):
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class ConfirmacionRecuperacionView(DjangoPasswordResetConfirmView):
    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            PasswordResetAuditEvent.objects.create(
                user=self.user,
                action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
                email_fingerprint=_fingerprint(
                    f'email:{self.user.email.strip().casefold()}'
                ),
                ip_address=_request_ip(self.request),
            )
        return response
