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
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import password_validators_help_text_html
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_http_methods

from AdminApp.models import (
    AccountActivationToken,
    PasswordResetAuditEvent,
    PasswordResetCode,
    PasswordResetLinkToken,
    PasswordResetRateLimitKey,
    Usuario,
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
    email = forms.CharField(
        label='Correo electrónico o nombre de usuario',
        max_length=120,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'username',
            'autofocus': True,
            'placeholder': 'ejemplo@munilaserena.cl o tu usuario',
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


def _email_fingerprint(value):
    return _fingerprint(f'email:{value.strip().casefold()}')


def _request_ip(request):
    remote_addr = request.META.get('REMOTE_ADDR', '')
    if not remote_addr:
        return None
    try:
        return str(ipaddress.ip_address(remote_addr))
    except ValueError:
        logger.warning('REMOTE_ADDR inválida al solicitar recuperación de contraseña.')
        return None


def _send_html_email(user, *, subject, body, html_body, email_kind):
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_body, 'text/html')
        logo_path = settings.BASE_DIR / 'static' / 'img' / 'logo.png'
        if logo_path.exists():
            with logo_path.open('rb') as logo_file:
                logo = MIMEImage(logo_file.read(), _subtype='png')
            logo.add_header('Content-ID', '<logo_serena>')
            logo.add_header('Content-Disposition', 'inline', filename='logo.png')
            email.attach(logo)
        sent = email.send(fail_silently=False)
    except (smtplib.SMTPException, OSError):
        logger.exception(
            'No se pudo enviar el correo (%s) al usuario id=%s.',
            email_kind,
            user.pk,
        )
        return False
    if sent != 1:
        logger.error(
            'El backend de correo no confirmó el envío (%s) al usuario id=%s.',
            email_kind,
            user.pk,
        )
        return False
    return True


def _invalidate_all_recovery_tokens(user):
    now = timezone.now()
    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    PasswordResetLinkToken.objects.filter(user=user, used_at__isnull=True).update(used_at=now)


def _complete_account_activation_if_needed(user):
    updates = []
    if getattr(user, 'requiere_cambio_password', False):
        user.requiere_cambio_password = False
        updates.append('requiere_cambio_password')
    if getattr(user, 'estado', '') == Usuario.EstadoCuenta.PENDIENTE_ACTIVACION:
        user.estado = Usuario.EstadoCuenta.ACTIVO
        updates.append('estado')
    if getattr(user, 'fecha_activacion', None) is None:
        user.fecha_activacion = timezone.now()
        updates.append('fecha_activacion')
    if updates:
        user.save(update_fields=updates)
    AccountActivationToken.objects.filter(user=user, used_at__isnull=True).update(
        used_at=timezone.now(),
    )


def emitir_y_enviar_activacion(user, temp_password=None):
    now = timezone.now()
    raw_token = secrets.token_urlsafe(32)
    token_hash = _fingerprint(f'activation:{user.pk}:{raw_token}')
    ttl = getattr(settings, 'ACCOUNT_ACTIVATION_TOKEN_TTL_SECONDS', 86400)

    with transaction.atomic():
        record = AccountActivationToken.objects.select_for_update().filter(user=user).first()
        if record is None:
            record = AccountActivationToken(user=user)
        record.token_hash = token_hash
        record.expires_at = now + timedelta(seconds=ttl)
        record.last_sent_at = now
        record.used_at = None
        record.save()

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse('activar_cuenta', kwargs={'uidb64': uidb64, 'token': raw_token})
    activation_url = f'{settings.PASSWORD_RESET_PROTOCOL}://{settings.PASSWORD_RESET_DOMAIN}{path}'
    hours = max(1, ceil(ttl / 3600))
    context = {
        'nombre': user.nombre or user.get_full_name() or user.email,
        'email': user.email,
        'activation_url': activation_url,
        'temp_password': temp_password,
        'horas': hours,
    }
    body = (
        f'Hola {context["nombre"]},\n\n'
        'Se ha creado tu cuenta en el Sistema de Gestión de Resultados (SGR).\n'
        f'Usuario / Correo: {user.email}\n'
        + (f'Credencial temporal de primer ingreso: {temp_password}\n' if temp_password else '')
        + f'\nActiva tu cuenta y define tu contraseña definitiva en el siguiente enlace '
        f'(válido por {hours} horas y de un solo uso):\n{activation_url}\n\n'
        'Sistema de Gestión de Resultados\nIlustre Municipalidad de La Serena'
    )
    html_body = render_to_string('emails/activar_cuenta.html', context)
    return _send_html_email(
        user,
        subject='Activación de cuenta - Sistema de Gestión de Resultados (SGR)',
        body=body,
        html_body=html_body,
        email_kind='activación de cuenta',
    )


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user
            and user.is_authenticated
            and getattr(user, 'requiere_cambio_password', False)
        ):
            allowed_prefixes = (
                '/accounts/primer-ingreso/',
                '/accounts/logout/',
                '/accounts/activar/',
                '/static/',
                '/media/',
            )
            if not any(request.path.startswith(prefix) for prefix in allowed_prefixes):
                return redirect('primer_ingreso')
        return self.get_response(request)


@require_http_methods(['GET', 'POST'])
def activar_cuenta(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        user_id = None

    now = timezone.now()
    User = get_user_model()
    user = User._default_manager.filter(pk=user_id, is_active=True).first() if user_id else None
    record = (
        AccountActivationToken.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).first()
        if user else None
    )
    expected_hash = _fingerprint(f'activation:{user.pk}:{token}') if user else ''
    validlink = bool(record and hmac.compare_digest(record.token_hash, expected_hash))

    if not validlink:
        return render(request, 'auth/account_activate.html', {
            'form': None,
            'validlink': False,
            'password_requirements': password_validators_help_text_html(),
        })

    form = NuevaContrasenaForm(user=user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            locked_record = AccountActivationToken.objects.select_for_update().filter(
                user=user,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).first()
            if not locked_record or not hmac.compare_digest(locked_record.token_hash, expected_hash):
                return render(request, 'auth/account_activate.html', {
                    'form': None,
                    'validlink': False,
                    'password_requirements': password_validators_help_text_html(),
                })
            activated_user = form.save()
            locked_record.used_at = timezone.now()
            locked_record.save(update_fields=['used_at'])
            _complete_account_activation_if_needed(activated_user)
            _invalidate_all_recovery_tokens(activated_user)

        messages.success(request, 'Tu cuenta fue activada y tu contraseña definitiva quedó guardada. Ya puedes iniciar sesión.')
        return redirect('login')

    return render(request, 'auth/account_activate.html', {
        'form': form,
        'validlink': True,
        'target_user': user,
        'password_requirements': password_validators_help_text_html(),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def primer_ingreso(request):
    if not getattr(request.user, 'requiere_cambio_password', False):
        return redirect('home')

    form = NuevaContrasenaForm(user=request.user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            _complete_account_activation_if_needed(user)
            _invalidate_all_recovery_tokens(user)
        update_session_auth_hash(request, user)
        messages.success(request, 'Contraseña definitiva creada correctamente. Bienvenido al sistema.')
        return redirect('home')

    return render(request, 'auth/primer_ingreso.html', {
        'form': form,
        'password_requirements': password_validators_help_text_html(),
    })


def _record_request_event(request, identifier_fingerprint, user, now, force_limited=False):
    ip_address = _request_ip(request)
    lock_keys = [_fingerprint(f'id:{identifier_fingerprint}')]
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
        created_at__gte=now - timedelta(seconds=settings.PASSWORD_RESET_RATE_WINDOW),
    )
    limited_by_identifier = recent_requests.filter(
        email_fingerprint=identifier_fingerprint,
    ).count() >= settings.PASSWORD_RESET_RATE_LIMIT
    limited_by_ip = bool(
        ip_address
        and recent_requests.filter(ip_address=ip_address).count() >= settings.PASSWORD_RESET_RATE_LIMIT
    )
    limited = force_limited or limited_by_identifier or limited_by_ip
    PasswordResetAuditEvent.objects.create(
        user=user,
        action=PasswordResetAuditEvent.Action.REQUEST,
        email_fingerprint=identifier_fingerprint,
        ip_address=ip_address,
        was_rate_limited=limited,
    )
    return limited


def _find_user_by_identifier(queryset, identifier):
    clean = (identifier or '').strip()
    if not clean:
        return None
    return queryset.filter(
        Q(email__iexact=clean) | Q(nombre__iexact=clean),
        is_active=True,
    ).first()


def _matching_code_record(email_fingerprint, *, lock=False):
    records = PasswordResetCode.objects.filter(
        email_fingerprint=email_fingerprint,
    ).select_related('user').order_by('-last_sent_at')
    if lock:
        records = records.select_for_update()
    for record in records:
        if hmac.compare_digest(record.email_fingerprint, email_fingerprint):
            return record
    return None


def _replace_code(record, user, email_fingerprint, now):
    code = f'{secrets.randbelow(1_000_000):06d}'
    if record is None:
        record = PasswordResetCode(user=user)
    record.email_fingerprint = email_fingerprint
    record.code_hash = make_password(code)
    record.expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_CODE_TTL_SECONDS)
    record.last_sent_at = now
    record.failed_attempts = 0
    record.verified_at = None
    record.used_at = None
    record.save()
    return code


def _request_code(request, identifier_fingerprint, *, identifier=None, force_limited=False):
    now = timezone.now()
    user = None
    code = None
    with transaction.atomic():
        User = get_user_model()
        if identifier is not None:
            user = _find_user_by_identifier(User._default_manager.select_for_update(), identifier)
        else:
            record = _matching_code_record(identifier_fingerprint, lock=True)
            if record and record.user.is_active:
                user = record.user

        limited = _record_request_event(
            request,
            identifier_fingerprint,
            user,
            now,
            force_limited=force_limited,
        )
        if user and not limited:
            record = PasswordResetCode.objects.select_for_update().filter(user=user).first()
            code = _replace_code(record, user, identifier_fingerprint, now)
    return user, code, limited, now


def _send_recovery_code(user, code):
    minutes = ceil(settings.PASSWORD_RESET_CODE_TTL_SECONDS / 60)
    body = (
        f'Hola {user.nombre or user.get_full_name() or user.email},\n\n'
        f'Tu código de recuperación de SGR es: {code}\n'
        f'El código vence en {minutes} minutos y solo puede utilizarse una vez.\n\n'
        'Si no solicitaste este cambio, puedes ignorar este mensaje.\n\n'
        'Sistema de Gestión de Resultados\n'
        'Ilustre Municipalidad de La Serena'
    )
    html_body = render_to_string(
        'emails/recuperar_codigo.html',
        {
            'nombre': user.nombre or user.get_full_name() or user.email,
            'codigo': code,
            'minutos': minutes,
        },
    )
    _send_html_email(
        user,
        subject='Código de recuperación de contraseña - SGR',
        body=body,
        html_body=html_body,
        email_kind='código de recuperación',
    )


def _request_link(request, identifier):
    now = timezone.now()
    identifier_fingerprint = _email_fingerprint(identifier)
    raw_token = None
    with transaction.atomic():
        User = get_user_model()
        user = _find_user_by_identifier(User._default_manager.select_for_update(), identifier)
        limited = _record_request_event(
            request,
            identifier_fingerprint,
            user,
            now,
        )
        if user and not limited:
            raw_token = secrets.token_urlsafe(32)
            link_record = PasswordResetLinkToken.objects.select_for_update().filter(user=user).first()
            if link_record is None:
                link_record = PasswordResetLinkToken(user=user)
            link_record.token_hash = _fingerprint(f'reset-link:{user.pk}:{raw_token}')
            link_record.expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
            link_record.used_at = None
            link_record.save()
    return user, raw_token, limited


def _send_recovery_link(user, raw_token):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse(
        'password_reset_confirm',
        kwargs={'uidb64': uidb64, 'token': raw_token},
    )
    reset_url = (
        f'{settings.PASSWORD_RESET_PROTOCOL}://'
        f'{settings.PASSWORD_RESET_DOMAIN}{path}'
    )
    minutes = ceil(settings.PASSWORD_RESET_TIMEOUT / 60)
    context = {
        'nombre': user.nombre or user.get_full_name() or user.email,
        'reset_url': reset_url,
        'minutos': minutes,
    }
    body = render_to_string('auth/password_reset_email.html', context)
    html_body = render_to_string('emails/recuperar_enlace.html', context)
    _send_html_email(
        user,
        subject='Enlace de recuperación de contraseña - SGR',
        body=body,
        html_body=html_body,
        email_kind='enlace de recuperación',
    )


def _active_user_from_uid(uidb64):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        return None
    User = get_user_model()
    return User._default_manager.filter(pk=user_id, is_active=True).first()


def _token_form_context(form, *, validlink):
    return {
        'form': form,
        'validlink': validlink,
        'current_step': 2,
        'password_requirements': password_validators_help_text_html(),
    }


def _resend_seconds_remaining(request, now=None):
    now = now or timezone.now()
    last_sent = request.session.get(SESSION_LAST_SENT_AT)
    if not isinstance(last_sent, (int, float)):
        return 0
    elapsed = now.timestamp() - last_sent
    return max(0, ceil(settings.PASSWORD_RESET_CODE_RESEND_SECONDS - elapsed))


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
        elif record and record.failed_attempts < settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS:
            record.failed_attempts += 1
            record.save(update_fields=['failed_attempts'])

        PasswordResetAuditEvent.objects.create(
            user=record.user if record else None,
            action=PasswordResetAuditEvent.Action.CODE_VALIDATION,
            email_fingerprint=email_fingerprint,
            ip_address=ip_address,
            was_rate_limited=bool(
                record
                and record.failed_attempts >= settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS
                and not valid
            ),
        )
    return valid


@require_http_methods(['GET', 'POST'])
def solicitar_recuperacion(request):
    form = SolicitudRecuperacionForm(request.POST or None)
    recovery_method = request.POST.get('method', request.GET.get('method', 'link'))
    if recovery_method not in {'link', 'code'}:
        recovery_method = 'link'

    if request.method == 'POST' and form.is_valid():
        identificador = form.cleaned_data['email']
        identifier_fingerprint = _email_fingerprint(identificador)
        request.session.pop(SESSION_VERIFIED_FINGERPRINT, None)
        if recovery_method == 'code':
            user, code, _, now = _request_code(
                request,
                identifier_fingerprint,
                identifier=identificador,
            )
            request.session[SESSION_EMAIL_FINGERPRINT] = identifier_fingerprint
            request.session[SESSION_LAST_SENT_AT] = now.timestamp()
            if user and code:
                _send_recovery_code(user, code)
            messages.info(
                request,
                'Si los datos ingresados corresponden a una cuenta registrada, '
                'recibirás las instrucciones en el correo asociado.',
            )
            return redirect('password_reset_code')

        user, raw_token, limited = _request_link(request, identificador)
        if user and raw_token and not limited:
            _send_recovery_link(user, raw_token)
        messages.info(
            request,
            'Si los datos ingresados corresponden a una cuenta registrada, '
            'recibirás un enlace de un solo uso en el correo asociado.',
        )
        return redirect('password_reset_done')

    return render(request, 'auth/password_reset_form.html', {
        'form': form,
        'current_step': 1,
        'recovery_method': recovery_method,
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
                'Si los datos corresponden a una cuenta registrada, enviaremos un nuevo código. '
                'Revisa tu correo y espera el contador para volver a solicitarlo.',
            )
            return redirect('password_reset_code')

        form = CodigoRecuperacionForm(request.POST)
        form_valid = form.is_valid()
        submitted_code = form.cleaned_data['code'] if form_valid else ''
        if _validate_code(request, email_fingerprint, submitted_code):
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
    record = _verified_code_record(email_fingerprint) if email_fingerprint else None
    if record is None:
        request.session.pop(SESSION_VERIFIED_FINGERPRINT, None)
        messages.error(request, 'Verifica un código vigente antes de crear una nueva contraseña.')
        return redirect('password_reset_code')

    form = NuevaContrasenaForm(user=record.user)
    if request.method == 'POST':
        form = NuevaContrasenaForm(user=record.user, data=request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked_record = _verified_code_record(email_fingerprint, lock=True)
                if locked_record is None:
                    messages.error(request, 'El código ya no está disponible. Solicita uno nuevo.')
                    return redirect('password_reset_code')

                form = NuevaContrasenaForm(user=locked_record.user, data=request.POST)
                if not form.is_valid():
                    return render(request, 'auth/password_reset_new.html', {
                        'form': form,
                        'current_step': 3,
                        'password_requirements': password_validators_help_text_html(),
                    })

                user = form.save()
                _complete_account_activation_if_needed(user)
                _invalidate_all_recovery_tokens(user)
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


@require_http_methods(['GET', 'POST'])
def confirmar_enlace_recuperacion(request, uidb64, token):
    user = _active_user_from_uid(uidb64)
    now = timezone.now()
    link_record = (
        PasswordResetLinkToken.objects.filter(
            user=user,
            used_at__isnull=True,
            expires_at__gt=now,
        ).first()
        if user else None
    )
    expected_hash = _fingerprint(f'reset-link:{user.pk}:{token}') if user else ''
    if not link_record or not hmac.compare_digest(link_record.token_hash, expected_hash):
        return render(
            request,
            'auth/password_reset_confirm.html',
            _token_form_context(None, validlink=False),
        )

    form = NuevaContrasenaForm(user=user)
    if request.method == 'POST':
        form = NuevaContrasenaForm(user=user, data=request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked_link = PasswordResetLinkToken.objects.select_for_update().filter(
                    user=user,
                    used_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ).first()
                if not locked_link or not hmac.compare_digest(locked_link.token_hash, expected_hash):
                    return render(
                        request,
                        'auth/password_reset_confirm.html',
                        _token_form_context(None, validlink=False),
                    )

                form = NuevaContrasenaForm(user=user, data=request.POST)
                if not form.is_valid():
                    return render(
                        request,
                        'auth/password_reset_confirm.html',
                        _token_form_context(form, validlink=True),
                    )
                changed_user = form.save()
                _complete_account_activation_if_needed(changed_user)
                _invalidate_all_recovery_tokens(changed_user)
                PasswordResetAuditEvent.objects.create(
                    user=changed_user,
                    action=PasswordResetAuditEvent.Action.PASSWORD_CHANGED,
                    email_fingerprint=_email_fingerprint(changed_user.email),
                    ip_address=_request_ip(request),
                )
            messages.success(request, 'Tu contraseña se actualizó correctamente.')
            return redirect('password_reset_complete')

    return render(
        request,
        'auth/password_reset_confirm.html',
        _token_form_context(form, validlink=True),
    )