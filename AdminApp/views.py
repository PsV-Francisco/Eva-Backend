import json
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from AdminApp.audit import registrar_historial
from AdminApp.forms import (
    HistorialFilterForm,
    ParametroSistemaForm,
    PasswordResetAuditFilterForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from AdminApp.models import (
    Cargo,
    Delegacion,
    Historial,
    ParametroSistema,
    PasswordResetAuditEvent,
    Usuario,
)
from AdminApp.maintainers import excel_response, maintainer
from config.decorators import cargo_required
from CoordinadorApp.authorization_forms import AuthorizationDecisionForm, AuthorizationRevokeForm
from CoordinadorApp.models import SolicitudAutorizacionPeriodo
from CoordinadorApp.services import _authorization_snapshot, expire_authorizations


def _user_snapshot(user):
    return {
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'delegacion_id': user.delegacion_id,
        'cargo_id': user.cargo_id,
        'roles': list(user.roles.order_by('pk').values_list('pk', flat=True)),
        'delegaciones_autorizadas': list(
            user.delegaciones_autorizadas.order_by('pk').values_list('pk', flat=True)
        ),
        'is_active': user.is_active,
    }


@cargo_required('admin', 'administrador', permission='access_admin_users')
def home(request):
    active_administrators = Usuario.objects.filter(
        is_active=True,
    ).filter(
        Q(is_superuser=True)
        | Q(cargo__nombre__iexact='admin')
        | Q(cargo__nombre__iexact='administrador')
    )
    administrator_ids = list(
        active_administrators.values_list('pk', flat=True)[:2]
    )
    last_active_admin_id = (
        administrator_ids[0] if len(administrator_ids) == 1 else None
    )
    status_filter = request.GET.get('estado', '')
    if status_filter not in {'', 'activo', 'inactivo'}:
        return HttpResponseBadRequest('Filtro de estado no válido.')
    delegation_filter = request.GET.get('delegacion', '')
    if delegation_filter and (
        not delegation_filter.isdecimal()
        or not Delegacion.objects.filter(pk=delegation_filter).exists()
    ):
        return HttpResponseBadRequest('Filtro de delegación no válido.')
    if request.GET.get('export', '') not in {'', 'excel'}:
        return HttpResponseBadRequest('Formato de exportación no válido.')

    edit_id = request.GET.get('editar')
    editing_user = None
    if edit_id:
        editing_user = get_object_or_404(Usuario, pk=edit_id)

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        if action not in {'guardar', 'eliminar', 'cambiar_estado'}:
            return HttpResponseBadRequest('Acción no válida.')
        target_id = request.POST.get('usuario_id')
        if action == 'eliminar':
            target = get_object_or_404(Usuario, pk=target_id)
            if target.pk == request.user.pk or target.is_superuser or target.is_staff:
                messages.error(request, 'No se pueden eliminar cuentas propias o con privilegios administrativos.')
            else:
                try:
                    before = _user_snapshot(target)
                    entity = f'Usuario:{target.pk}'
                    with transaction.atomic():
                        target.delete()
                        registrar_historial(
                            actor=request.user,
                            action='Eliminar usuario',
                            entity=entity,
                            before=before,
                        )
                    messages.success(request, 'La cuenta se eliminó correctamente.')
                except ProtectedError as error:
                    if 'último Administrador' in str(error):
                        messages.error(request, 'No se puede eliminar al último Administrador activo.')
                    else:
                        messages.error(request, 'No se puede eliminar esta cuenta porque tiene información asociada.')
            return redirect('administracion:home')

        if action == 'cambiar_estado':
            target = get_object_or_404(Usuario, pk=target_id)
            if target.pk == request.user.pk or target.is_superuser:
                messages.error(request, 'No puedes desactivar tu propia cuenta ni otra cuenta superadministradora.')
            else:
                before = _user_snapshot(target)
                try:
                    with transaction.atomic():
                        target.is_active = not target.is_active
                        target.save(update_fields=['is_active'])
                        registrar_historial(
                            actor=request.user,
                            action='Cambiar estado de usuario',
                            entity=f'Usuario:{target.pk}',
                            before=before,
                            after=_user_snapshot(target),
                        )
                    messages.success(request, 'El estado del usuario se actualizó correctamente.')
                except ValidationError as error:
                    messages.error(request, str(error))
            return redirect('administracion:home')

        if target_id:
            editing_user = get_object_or_404(Usuario, pk=target_id)
            form = UsuarioUpdateForm(
                request.POST,
                instance=editing_user,
                protected_admin=editing_user.pk == last_active_admin_id,
                actor=request.user,
            )
        else:
            form = UsuarioCreationForm(request.POST, actor=request.user)

        before = _user_snapshot(editing_user) if target_id else None
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    after = _user_snapshot(user)
                    registrar_historial(
                        actor=request.user,
                        action='Editar usuario' if target_id else 'Crear usuario',
                        entity=f'Usuario:{user.pk}',
                        before=before,
                        after=after,
                    )
                    previous_roles = before['roles'] if before else []
                    if previous_roles != after['roles']:
                        registrar_historial(
                            actor=request.user,
                            action='Cambiar asignación de roles',
                            entity=f'Usuario:{user.pk}',
                            before={'roles': previous_roles},
                            after={'roles': after['roles']},
                        )
                messages.success(
                    request,
                    'La cuenta se actualizó correctamente.' if target_id
                    else 'El usuario quedó creado correctamente.',
                )
                return redirect('administracion:home')
            except ValidationError as error:
                form.add_error(None, error)
                messages.error(request, 'No se pudo guardar la cuenta: revisa las restricciones de administración.')
        messages.error(request, 'Revisa los campos del formulario.')
    else:
        form = (
            UsuarioUpdateForm(
                instance=editing_user,
                protected_admin=editing_user.pk == last_active_admin_id,
                actor=request.user,
            )
            if editing_user else UsuarioCreationForm(actor=request.user)
        )

    users = Usuario.objects.select_related(
        'delegacion', 'cargo',
    ).prefetch_related('roles', 'delegaciones_autorizadas')
    query = request.GET.get('q', '').strip()
    if query:
        search = Q()
        for field in (
            'email', 'first_name', 'last_name', 'cargo__nombre',
            'delegacion__nombre', 'roles__nombre',
            'delegaciones_autorizadas__nombre',
        ):
            search |= Q(**{f'{field}__icontains': query})
        users = users.filter(search)
    status = status_filter
    if status == 'activo':
        users = users.filter(is_active=True)
    elif status == 'inactivo':
        users = users.filter(is_active=False)
    delegation_id = delegation_filter
    if delegation_id.isdecimal():
        users = users.filter(
            Q(delegacion_id=delegation_id)
            | Q(delegaciones_autorizadas__pk=delegation_id)
        )
    users = users.distinct().order_by('email')
    if request.GET.get('export') == 'excel':
        return excel_response(
            users,
            (
                ('Correo electrónico', 'email'),
                ('Nombre', 'first_name'),
                ('Apellido', 'last_name'),
                ('Cargo', 'cargo__nombre'),
                ('Delegación principal', 'delegacion__nombre'),
                ('Delegaciones autorizadas', 'delegaciones_autorizadas'),
                ('Roles', 'roles'),
                ('Estado', 'is_active'),
            ),
            'usuarios',
        )
    user_page = Paginator(users, 25).get_page(request.GET.get('page'))
    pagination_parameters = request.GET.copy()
    for key in ('page', 'export', 'editar'):
        pagination_parameters.pop(key, None)
    pagination_query = pagination_parameters.urlencode()

    context = {
        'sgr_role': 'Administración',
        'form': form,
        'editing_user': editing_user,
        'last_active_admin_id': last_active_admin_id,
        'users': user_page.object_list,
        'page_obj': user_page,
        'pagination_query': pagination_query,
        'query': query,
        'status': status,
        'delegation_id': delegation_id,
        'has_filters': bool(query or status or delegation_id),
        'base_user_count': Usuario.objects.count(),
        'delegations': Delegacion.objects.order_by('nombre'),
        'user_count': Usuario.objects.count(),
        'delegation_count': Delegacion.objects.count(),
        'position_count': Cargo.objects.count(),
    }
    return render(request, 'AdminApp/index.html', context)


@cargo_required('admin', 'administrador', permission='access_admin_parameters')
def parametros(request):
    keys = {
        'tope_cumplimiento': ParametroSistema.Clave.TOPE_CUMPLIMIENTO,
        'umbral_delegacion': ParametroSistema.Clave.UMBRAL_DELEGACION,
        'max_dias_autorizacion': ParametroSistema.Clave.MAX_DIAS_AUTORIZACION,
    }
    form = ParametroSistemaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            for field, key in keys.items():
                previous = ParametroSistema.obtener(key)
                parameter, _ = ParametroSistema.objects.get_or_create(
                    clave=key,
                    defaults={'valor': form.cleaned_data[field]},
                )
                new_value = form.cleaned_data[field]
                if previous != new_value:
                    parameter.valor = new_value
                    parameter.save(update_fields=['valor'])
                    registrar_historial(
                        actor=request.user,
                        action='Cambiar parámetro del sistema',
                        entity=f'ParametroSistema:{key}',
                        before={'valor': str(previous)},
                        after={'valor': str(new_value)},
                    )
        messages.success(request, 'Los parámetros se actualizaron correctamente.')
        return redirect('administracion:parametros')
    if request.method == 'POST':
        messages.error(request, 'Revisa los valores y rangos permitidos.')
    return render(request, 'AdminApp/parametros.html', {
        'sgr_role': 'Administración',
        'form': form,
        'sidebar_modules': (
            {'label': 'Usuarios', 'url_name': 'administracion:home'},
            {'label': 'Parámetros del sistema', 'url_name': 'administracion:parametros'},
        ),
    })


@cargo_required('admin', 'administrador', permission='access_admin_delegations')
def delegaciones(request):
    return maintainer(request, 'delegaciones')


@cargo_required('admin', 'administrador', permission='access_admin_positions')
def cargos(request):
    return maintainer(request, 'cargos')


@cargo_required('admin', 'administrador', permission='access_admin_functions')
def funciones(request):
    return maintainer(request, 'funciones')


@cargo_required('admin', 'administrador', permission='access_admin_position_functions')
def cargos_funciones(request):
    return maintainer(request, 'cargos-funciones')


@cargo_required('admin', 'administrador', permission='access_admin_catalog')
def catalogo(request):
    return maintainer(request, 'catalogo')


@cargo_required('admin', 'administrador', permission='access_admin_roles')
def roles(request):
    return maintainer(request, 'roles')


@cargo_required('coordinador', 'admin', 'administrador', permission='access_admin_items')
def items(request):
    return maintainer(request, 'items')


@cargo_required('admin', 'administrador', permission='access_admin_attention_types')
def tipos_atencion(request):
    return maintainer(request, 'tipos-atencion')


@cargo_required('admin', 'administrador', permission='access_admin_subattentions')
def subatenciones(request):
    return maintainer(request, 'subatenciones')


@cargo_required('coordinador', 'admin', 'administrador', permission='access_admin_goals')
def metas(request):
    return maintainer(request, 'metas')


@cargo_required(
    'admin', 'administrador', permission='review_closed_period_authorizations',
)
def solicitudes_autorizacion(request):
    expire_authorizations()
    if request.method == 'POST':
        solicitud = get_object_or_404(
            SolicitudAutorizacionPeriodo.objects.select_related('periodo'),
            pk=request.POST.get('solicitud_id'),
        )
        action = request.POST.get('action')
        before = _authorization_snapshot(solicitud)
        if action in {'aprobar', 'rechazar'} and solicitud.estado != SolicitudAutorizacionPeriodo.Estado.PENDIENTE:
            messages.error(request, 'Solo se pueden resolver solicitudes pendientes.')
        elif action == 'aprobar':
            form = AuthorizationDecisionForm(request.POST)
            if form.is_valid():
                solicitud.estado = SolicitudAutorizacionPeriodo.Estado.APROBADA
                solicitud.aprobador = request.user
                solicitud.comentario_aprobador = form.cleaned_data['comentario']
                solicitud.vence_en = form.cleaned_data['vence_en']
                solicitud.decidida_en = timezone.now()
                solicitud.save(update_fields=['estado', 'aprobador', 'comentario_aprobador', 'vence_en', 'decidida_en'])
                registrar_historial(actor=request.user, action='Aprobar autorización de período', entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}', before=before, after=_authorization_snapshot(solicitud), period=solicitud.periodo)
                messages.success(request, 'La autorización quedó vigente hasta la fecha indicada.')
                return redirect('administracion:solicitudes-autorizacion')
            messages.error(request, 'Revisa la fecha de vencimiento y el comentario.')
        elif action == 'rechazar':
            form = AuthorizationDecisionForm(request.POST)
            if form.is_valid() and form.cleaned_data['comentario'].strip():
                solicitud.estado = SolicitudAutorizacionPeriodo.Estado.RECHAZADA
                solicitud.aprobador = request.user
                solicitud.comentario_aprobador = form.cleaned_data['comentario']
                solicitud.decidida_en = timezone.now()
                solicitud.save(update_fields=['estado', 'aprobador', 'comentario_aprobador', 'decidida_en'])
                registrar_historial(actor=request.user, action='Rechazar autorización de período', entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}', before=before, after=_authorization_snapshot(solicitud), period=solicitud.periodo)
                messages.success(request, 'La solicitud fue rechazada.')
                return redirect('administracion:solicitudes-autorizacion')
            messages.error(request, 'El rechazo requiere un comentario.')
        elif action == 'revocar' and solicitud.estado == SolicitudAutorizacionPeriodo.Estado.APROBADA:
            form = AuthorizationRevokeForm(request.POST)
            if form.is_valid():
                solicitud.estado = SolicitudAutorizacionPeriodo.Estado.REVOCADA
                solicitud.aprobador = request.user
                solicitud.comentario_aprobador = form.cleaned_data['comentario']
                solicitud.revocada_en = timezone.now()
                solicitud.decidida_en = timezone.now()
                solicitud.save(update_fields=['estado', 'aprobador', 'comentario_aprobador', 'revocada_en', 'decidida_en'])
                registrar_historial(actor=request.user, action='Revocar autorización de período', entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}', before=before, after=_authorization_snapshot(solicitud), period=solicitud.periodo)
                messages.success(request, 'La autorización fue revocada.')
                return redirect('administracion:solicitudes-autorizacion')
            messages.error(request, 'La revocación requiere un comentario.')
    solicitudes = SolicitudAutorizacionPeriodo.objects.select_related(
        'periodo', 'solicitante', 'aprobador',
    ).prefetch_related('funcionarios')
    now = timezone.now()
    for solicitud in solicitudes:
        solicitud.es_antigua = (
            solicitud.estado == SolicitudAutorizacionPeriodo.Estado.PENDIENTE
            and solicitud.creada_en <= now - timedelta(days=3)
        )
    return render(request, 'AdminApp/solicitudes_autorizacion.html', {
        'sgr_role': 'Administración',
        'solicitudes': solicitudes,
        'sidebar_modules': (
            {'label': 'Usuarios', 'url_name': 'administracion:home'},
            {'label': 'Solicitudes de autorización', 'url_name': 'administracion:solicitudes-autorizacion'},
        ),
    })


@cargo_required('admin', 'administrador', permission='access_admin_history')
@require_GET
def historial(request):
    actions = Historial.objects.order_by().values_list(
        'accion', flat=True,
    ).distinct()
    form = HistorialFilterForm(request.GET or None, actions=actions)
    if not form.is_valid():
        return HttpResponseBadRequest('Revisa los filtros del historial.')

    entries = Historial.objects.select_related(
        'autor', 'periodo',
    ).order_by('-fecha_modificacion')
    query = form.cleaned_data['q']
    if query:
        entries = entries.filter(
            Q(accion__icontains=query)
            | Q(entidad_afectada__icontains=query)
            | Q(autor__email__icontains=query)
            | Q(periodo__nombre__icontains=query)
        )
    if form.cleaned_data['accion']:
        entries = entries.filter(accion=form.cleaned_data['accion'])
    if form.cleaned_data['desde']:
        entries = entries.filter(
            fecha_modificacion__date__gte=form.cleaned_data['desde'],
        )
    if form.cleaned_data['hasta']:
        entries = entries.filter(
            fecha_modificacion__date__lte=form.cleaned_data['hasta'],
        )

    page_obj = Paginator(entries, 25).get_page(request.GET.get('page'))
    rows = [{
        'values': (
            entry.fecha_modificacion,
            entry.accion,
            entry.entidad_afectada,
            entry.autor.email,
            entry.periodo.nombre if entry.periodo_id else '',
            json.dumps(entry.valor_anterior, ensure_ascii=False),
            json.dumps(entry.valor_nuevo, ensure_ascii=False),
        ),
    } for entry in page_obj.object_list]
    return render(request, 'AdminApp/audit_viewer.html', {
        'sgr_role': 'Administración',
        'page_title': 'Historial del sistema',
        'columns': (
            'Fecha', 'Acción', 'Entidad', 'Autor', 'Período',
            'Valor anterior', 'Valor nuevo',
        ),
        'rows': rows,
        'filter_form': form,
        'page_obj': page_obj,
        'pagination_query': _audit_pagination_query(request),
        'result_count': entries.count(),
        'route_name': 'administracion:historial',
    })


@cargo_required('admin', 'administrador', permission='access_admin_password_audit')
@require_GET
def password_reset_audit(request):
    form = PasswordResetAuditFilterForm(request.GET or None)
    if not form.is_valid():
        return HttpResponseBadRequest('Revisa los filtros de auditoría.')

    entries = PasswordResetAuditEvent.objects.select_related(
        'user',
    ).order_by('-created_at')
    query = form.cleaned_data['q']
    if query:
        entries = entries.filter(
            Q(user__email__icontains=query)
            | Q(email_fingerprint__icontains=query)
            | Q(ip_address__icontains=query)
        )
    if form.cleaned_data['accion']:
        entries = entries.filter(action=form.cleaned_data['accion'])
    limited = form.cleaned_data['limitada']
    if limited:
        entries = entries.filter(was_rate_limited=(limited == 'si'))
    if form.cleaned_data['desde']:
        entries = entries.filter(created_at__date__gte=form.cleaned_data['desde'])
    if form.cleaned_data['hasta']:
        entries = entries.filter(created_at__date__lte=form.cleaned_data['hasta'])

    page_obj = Paginator(entries, 25).get_page(request.GET.get('page'))
    rows = [{
        'values': (
            entry.created_at,
            entry.get_action_display(),
            entry.user.email if entry.user_id else '',
            entry.ip_address or '',
            'Sí' if entry.was_rate_limited else 'No',
        ),
    } for entry in page_obj.object_list]
    return render(request, 'AdminApp/audit_viewer.html', {
        'sgr_role': 'Administración',
        'page_title': 'Auditoría de recuperación de contraseña',
        'columns': ('Fecha', 'Evento', 'Usuario', 'Dirección IP', 'Límite aplicado'),
        'rows': rows,
        'filter_form': form,
        'page_obj': page_obj,
        'pagination_query': _audit_pagination_query(request),
        'result_count': entries.count(),
        'route_name': 'administracion:auditoria-recuperacion',
    })


def _audit_pagination_query(request):
    parameters = request.GET.copy()
    parameters.pop('page', None)
    return parameters.urlencode()
