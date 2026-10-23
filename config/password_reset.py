import hashlib
import hmac
import ipaddress
import logging
import secrets
import smtplib
from datetime import timedelta
from email.mime.image import MIMEImage
from math import ceil

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import password_validators_help_text_html
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from AdminApp.models import (
    PasswordResetAuditEvent,
    PasswordResetCode,
    PasswordResetRateLimitKey,
)

logger = logging.getLogger(__name__)

SESSION_EMAIL_FINGERPRINT = 'password_reset_email_fingerprint'
SESSION_LAST_SENT_AT = 'password_reset_last_sent_at'
SESSION_VERIFIED_FINGERPRINT = 'password_reset_verified_fingerprint'


class FormularioAcceso(AuthenticationForm):
    username = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )


class SolicitudRecuperacionForm(forms.Form):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'email',
            'autofocus': True,
        }),
    )


class CodigoRecuperacionForm(forms.Form):
    code = forms.RegexField(
        regex=r'^\d{6}$',
        max_length=6,
        min_length=6,
        error_messages={
            'invalid': 'Ingresa un código de seis dígitos.',
            'min_length': 'Ingresa un código de seis dígitos.',
            'max_length': 'Ingresa un código de seis dígitos.',
        },
    )


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


def _email_fingerprint(email):
    return _fingerprint(f'email:{email.strip().casefold()}')


def _request_ip(request):
    remote_addr = request.META.get('REMOTE_ADDR', '')
    if not remote_addr:
        return None
    try:
        return str(ipaddress.ip_address(remote_addr))
    except ValueError:
        logger.warning('REMOTE_ADDR inválida al solicitar recuperación de contraseña.')
        return None


def _record_request_event(request, email_fingerprint, user, now, force_limited=False):
    ip_address = _request_ip(request)
    lock_keys = [_fingerprint(f'email:{email_fingerprint}')]
    if ip_address:
        lock_keys.append(_fingerprint(f'ip:{ip_address}'))

    PasswordResetRateLimitKey.objects.bulk_create(
        [PasswordResetRateLimitKey(key=key) for key in lock_keys],
        ignore_conflicts=True,
    )
    list(
        PasswordResetRateLimitKey.objects.select_for_update()
        .filter(key__in=lock_keys)
        .order_by('key')
    )

    recent_requests = PasswordResetAuditEvent.objects.filter(
        action=PasswordResetAuditEvent.Action.REQUEST,
        created_at__gte=now - timedelta(
            seconds=settings.PASSWORD_RESET_RATE_WINDOW
        ),
    )
    limited_by_email = recent_requests.filter(
        email_fingerprint=email_fingerprint,
    ).count() >= settings.PASSWORD_RESET_RATE_LIMIT
    limited_by_ip = bool(
        ip_address
        and recent_requests.filter(ip_address=ip_address).count()
        >= settings.PASSWORD_RESET_RATE_LIMIT
    )
    limited = force_limited or limited_by_email or limited_by_ip
    PasswordResetAuditEvent.objects.create(
        user=user,
        action=PasswordResetAuditEvent.Action.REQUEST,
        email_fingerprint=email_fingerprint,
        ip_address=ip_address,
        was_rate_limited=limited,
    )
    return limited


def _matching_code_record(email_fingerprint, *, lock=False):
    records = PasswordResetCode.objects.filter(
        email_fingerprint=email_fingerprint,
    ).select_related('user').order_by('-last_sent_at')
    if lock:
        records = records.select_for_update()
    for record in records:
        current_fingerprint = _email_fingerprint(record.user.email)
        if hmac.compare_digest(current_fingerprint, email_fingerprint):
            return record
    return None


def _replace_code(record, user, email_fingerprint, now):
    code = f'{secrets.randbelow(1_000_000):06d}'
    if record is None:
        record = PasswordResetCode(user=user)
    record.email_fingerprint = email_fingerprint
    record.code_hash = make_password(code)
    record.expires_at = now + timedelta(
        seconds=settings.PASSWORD_RESET_CODE_TTL_SECONDS,
    )
    record.last_sent_at = now
    record.failed_attempts = 0
    record.verified_at = None
    record.used_at = None
    record.save()
    return code


def _request_code(request, email_fingerprint, *, email=None, force_limited=False):
    now = timezone.now()
    user = None
    code = None
    with transaction.atomic():
        User = get_user_model()
        if email is not None:
            user = User._default_manager.select_for_update().filter(
                email__iexact=email,
                is_active=True,
            ).first()
        else:
            record = _matching_code_record(email_fingerprint, lock=True)
            if record and record.user.is_active:
                user = record.user

        limited = _record_request_event(
            request,
            email_fingerprint,
            user,
            now,
            force_limited=force_limited,
        )
        if user and not limited:
            record = PasswordResetCode.objects.select_for_update().filter(
                user=user,
            ).first()
            code = _replace_code(record, user, email_fingerprint, now)
    return user, code, limited, now


def _send_recovery_code(user, code):
    minutes = ceil(settings.PASSWORD_RESET_CODE_TTL_SECONDS / 60)
    body = (
        f'Hola {user.get_full_name() or user.email},\n\n'
        f'Tu código de recuperación de SGR es: {code}\n'
        f'El código vence en {minutes} '
        'minutos y solo puede utilizarse una vez.\n\n'
        'Si no solicitaste este cambio, puedes ignorar este mensaje.\n\n'
        'Sistema de Gestión de Resultados\n'
        'Ilustre Municipalidad de La Serena'
    )
    html_body = render_to_string(
        'emails/recuperar_codigo.html',
        {
            'nombre': user.get_full_name() or user.email,
            'codigo': code,
            'minutos': minutes,
        },
    )
    try:
        email = EmailMultiAlternatives(
            subject='Código de recuperación de contraseña - SGR',
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_body, 'text/html')
        logo_path = settings.BASE_DIR / 'static' / 'img' / 'logo.png'
        with logo_path.open('rb') as logo_file:
            logo = MIMEImage(logo_file.read(), _subtype='png')
        logo.add_header('Content-ID', '<logo_serena>')
        logo.add_header('Content-Disposition', 'inline', filename='logo.png')
        email.attach(logo)
        sent = email.send(fail_silently=False)
    except (smtplib.SMTPException, OSError):
        logger.exception(
            'No se pudo enviar el código de recuperación al usuario id=%s.',
            user.pk,
        )
        return
    if sent != 1:
        logger.error(
            'El backend de correo no confirmó el envío del código al usuario id=%s.',
            user.pk,
        )


def _resend_seconds_remaining(request, now=None):
    now = now or timezone.now()
    last_sent = request.session.get(SESSION_LAST_SENT_AT)
    if not isinstance(last_sent, (int, float)):
        return 0
    elapsed = now.timestamp() - last_sent
    return max(
        0,
        ceil(settings.PASSWORD_RESET_CODE_RESEND_SECONDS - elapsed),
    )


def _verified_code_record(email_fingerprint, *, now=None, lock=False):
    now = now or timezone.now()
    record = _matching_code_record(email_fingerprint, lock=lock)
    if (
        record
        and record.user.is_active
        and record.verified_at
        and record.used_at is None
        and record.expires_at > now
        and record.failed_attempts < settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
    ):
        return record
    return None


def _validate_code(request, email_fingerprint, submitted_code):
    now = timezone.now()
    ip_address = _request_ip(request)
    with transaction.atomic():
        record = _matching_code_record(email_fingerprint, lock=True)
        valid = bool(
            record
            and record.user.is_active
            and record.used_at is None
            and record.expires_at > now
            and record.failed_attempts < settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
            and check_password(submitted_code, record.code_hash)
        )
        if valid:
            record.verified_at = now
            record.save(update_fields=['verified_at'])
        elif (
            record
            and record.failed_attempts < settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
        ):
            record.failed_attempts += 1
            record.save(update_fields=['failed_attempts'])

        PasswordResetAuditEvent.objects.create(
            user=record.user if record else None,
            action=PasswordResetAuditEvent.Action.CODE_VALIDATION,
            email_fingerprint=email_fingerprint,
            ip_address=ip_address,
            was_rate_limited=bool(
                record
                and record.failed_attempts
                >= settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
                and not valid
            ),
        )
    return valid


@require_http_methods(['GET', 'POST'])
def solicitar_recuperacion(request):
    form = SolicitudRecuperacionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        email_fingerprint = _email_fingerprint(email)
        user, code, _, now = _request_code(
            request,
            email_fingerprint,
            email=email,
        )
        request.session[SESSION_EMAIL_FINGERPRINT] = email_fingerprint
        request.session[SESSION_LAST_SENT_AT] = now.timestamp()
        request.session.pop(SESSION_VERIFIED_FINGERPRINT, None)
        if user and code:
            _send_recovery_code(user, code)
        messages.info(
            request,
            'Si existe una cuenta activa con ese correo, enviaremos un código. '
            'Ingresa el código recibido para continuar.',
        )
        return redirect('password_reset_code')

    return render(request, 'auth/password_reset_form.html', {
        'form': form,
        'current_step': 1,
    })


@require_http_methods(['GET', 'POST'])
def verificar_codigo(request):
    email_fingerprint = request.session.get(SESSION_EMAIL_FINGERPRINT)
    if not email_fingerprint:
        messages.info(request, 'Primero solicita un código de recuperación.')
        return redirect('password_reset')

    form = CodigoRecuperacionForm()
    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        if action == 'resend':
            now = timezone.now()
            remaining = _resend_seconds_remaining(request, now)
            user, code, _, recorded_at = _request_code(
                request,
                email_fingerprint,
                force_limited=remaining > 0,
            )
            if remaining == 0:
                request.session[SESSION_LAST_SENT_AT] = recorded_at.timestamp()
            if user and code:
                _send_recovery_code(user, code)
            messages.info(
                request,
                'Si la cuenta activa existe, enviaremos un nuevo código. '
                'Revisa tu correo y espera el contador para volver a solicitarlo.',
            )
            return redirect('password_reset_code')

        form = CodigoRecuperacionForm(request.POST)
        form_valid = form.is_valid()
        submitted_code = form.cleaned_data['code'] if form_valid else ''
        if _validate_code(
            request,
            email_fingerprint,
            submitted_code,
        ):
            request.session.cycle_key()
            request.session[SESSION_VERIFIED_FINGERPRINT] = email_fingerprint
            return redirect('password_reset_new')
        messages.error(
            request,
            'El código no es válido o venció. Revisa los seis dígitos o solicita uno nuevo.',
        )

    return render(request, 'auth/password_reset_code.html', {
        'form': form,
        'current_step': 2,
        'resend_seconds': _resend_seconds_remaining(request),
    })


@require_http_methods(['GET', 'POST'])
def nueva_contrasena(request):
    email_fingerprint = request.session.get(SESSION_VERIFIED_FINGERPRINT)
    record = (
        _verified_code_record(email_fingerprint)
        if email_fingerprint else None
    )
    if record is None:
        request.session.pop(SESSION_VERIFIED_FINGERPRINT, None)
        messages.error(
            request,
            'Verifica un código vigente antes de crear una nueva contraseña.',
        )
        return redirect('password_reset_code')

    form = NuevaContrasenaForm(user=record.user)
    if request.method == 'POST':
        form = NuevaContrasenaForm(user=record.user, data=request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked_record = _verified_code_record(
                    email_fingerprint,
                    lock=True,
                )
                if locked_record is None:
                    messages.error(
                        request,
                        'El código ya no está disponible. Solicita uno nuevo.',
                    )
                    return redirect('password_reset_code')

                form = NuevaContrasenaForm(
                    user=locked_record.user,
                    data=request.POST,
                )
                if not form.is_valid():
                    return render(request, 'auth/password_reset_new.html', {
                        'form': form,
                        'current_step': 3,
                        'password_requirements': password_validators_help_text_html(),
                    })

                user = form.save()
                locked_record.used_at = timezone.now()
                locked_record.save(update_fields=['used_at'])
                PasswordResetAuditEvent.objects.create(
                    user=user,
                    action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
                    email_fingerprint=email_fingerprint,
                    ip_address=_request_ip(request),
                )

            request.session.pop(SESSION_EMAIL_FINGERPRINT, None)
            request.session.pop(SESSION_LAST_SENT_AT, None)
            request.session.pop(SESSION_VERIFIED_FINGERPRINT, None)
            messages.success(request, 'Tu contraseña se actualizó correctamente.')
            return redirect('password_reset_complete')

    return render(request, 'auth/password_reset_new.html', {
        'form': form,
        'current_step': 3,
        'password_requirements': password_validators_help_text_html(),
    })


def enlace_recuperacion_obsoleto(request, uidb64, token):
    messages.info(
        request,
        'La recuperación ahora se confirma con un código de seis dígitos. '
        'Solicita uno nuevo para continuar.',
    )
    return redirect('password_reset')
