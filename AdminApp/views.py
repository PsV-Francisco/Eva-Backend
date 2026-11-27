#Importaciones Django
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
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

#Importaciones de Modelos
from FuncionarioApp.models import Vecino,Registro
from AdminApp.models import (Cargo,Delegacion,Historial,ParametroSistema,PasswordResetAuditEvent,Usuario)
from CoordinadorApp.models import Periodo, SolicitudAutorizacionPeriodo,Item

#Importaciones de Formularios
from AdminApp.forms import ItemForm
from CoordinadorApp.authorization_forms import AuthorizationDecisionForm, AuthorizationRevokeForm
from AdminApp.forms import (HistorialFilterForm,ParametroSistemaForm,PasswordResetAuditFilterForm,UsuarioCreationForm,UsuarioUpdateForm)
from AdminApp.forms import DelegacionForm

#Otras Importaciones
from AdminApp.audit import registrar_historial
from AdminApp.maintainers import excel_response, maintainer
from config.decorators import cargo_required
from config.permissions import PERMISSION_BY_VIEW, can_access_permission
from CoordinadorApp.services import _authorization_snapshot, expire_authorizations
from config.decorators import cargo_required



ADMIN_DASHBOARD_LINK_GROUPS = (
    ('Organización', (
        ('Usuarios', 'administracion:home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles y permisos', 'administracion:roles'),
    )),
    ('Territorio', (
        ('Vecinos', 'administracion:vecinos'),
        ('Juntas de Vecinos', 'administracion:juntas'),
        ('Hitos', 'administracion:hitos'),
    )),
    ('Operación', (
        ('Buscar solicitantes', 'administracion:beneficiados'),
        ('Registros', 'administracion:registros'),
        ('Atenciones Sociales', 'administracion:atenciones-sociales'),
        ('Compromisos', 'administracion:compromisos'),
        ('Ausencias', 'administracion:ausencias'),
        ('Felicitaciones', 'administracion:felicitaciones'),
        ('Reclamos', 'administracion:reclamos'),
        ('Tipos de Atención', 'administracion:tipos-atencion'),
        ('Subatenciones', 'administracion:subatenciones'),
    )),
    ('Metas y seguimiento', (
        ('Ítems y metas', 'administracion:items'),
        ('Metas', 'administracion:metas'),
        ('Ajustes de Metas', 'administracion:ajustes-metas'),
        ('Ponderaciones', 'coordinador:ponderaciones'),
        ('Resumen de Delegación', 'administracion:resumen-delegacion'),
    )),
    ('Informes', (
        ('Informes de Coordinación', 'coordinador:informes'),
        ('Informes Generados', 'administracion:informes-generados'),
        ('Tendencias históricas', 'coordinador:tendencias'),
    )),
    ('Auditoría', (
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
        ('Solicitudes de autorización', 'administracion:solicitudes-autorizacion'),
    )),
    ('Territorio', (
        ('Territorios', 'administracion:territorios'),
        ('Vecinos', 'administracion:vecinos'),
        ('Juntas de Vecinos', 'administracion:juntas'),
        ('Hitos', 'administracion:hitos'),
    )
))


def _admin_dashboard_modules(user):
    modules = []
    for label, shortcuts in ADMIN_DASHBOARD_LINK_GROUPS:
        links = []
        for link_label, route_name in shortcuts:
            definition = PERMISSION_BY_VIEW.get(route_name)
            if definition and can_access_permission(
                user,
                definition.codename,
                definition.cargos,
            ):
                links.append({
                    'label': link_label,
                    'url_name': route_name,
                })
        if links:
            modules.append({'label': label, 'links': links})
    return modules

@cargo_required('admin', 'administrador', permission='access_admin_beneficiados')
def beneficiados(request):
    return beneficiados_vista(request)

@cargo_required('admin', 'administrador', permission='create_admin_beneficiados')
@require_POST
def crear_beneficiado_ajax(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    telefono = data.get('telefono')
    email = data.get('email', '').strip() or None
    rut = data.get('rut', '').strip() or None

    if not nombre or not telefono:
        return JsonResponse({'success': False, 'message': 'Por favor completa los campos requeridos.'}, status=400)

    # Nota: Si el modelo Vecino exige territorio, delegación o junta en tu BD, 
    # asegúrate de asignarlos por defecto o requerirlos en el JSON.
    vecino = Vecino.objects.create(
        nombre=nombre,
        telefono=telefono,
        email=email,
        rut=rut,
    )
    return JsonResponse({'success': True, 'id': vecino.pk})

@cargo_required('admin', 'administrador', permission='view_admin_beneficiados_detail')
@require_GET
def detalle_beneficiado_json(request, beneficiado_id):
    b = get_object_or_404(Vecino, pk=beneficiado_id)
    return JsonResponse({
        'id': b.pk,
        'nombre': b.nombre,
        'apellido': '',  # Vecino unifica el nombre completo en 'nombre'
        'telefono': b.telefono or '',
        'email': b.email or '',
        'rut': b.rut or '',
    })


@cargo_required('admin', 'administrador', permission='edit_admin_beneficiados')
@require_POST
def editar_beneficiado_ajax(request, beneficiado_id):
    b = get_object_or_404(Vecino, pk=beneficiado_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    b.nombre = data.get('nombre', '').strip()
    b.telefono = data.get('telefono')
    b.email = data.get('email', '').strip() or None
    if 'rut' in data:
        b.rut = data.get('rut', '').strip() or None
    b.save()
    return JsonResponse({'success': True})

@cargo_required('admin', 'administrador', permission='delete_admin_beneficiados')
@require_POST
def eliminar_beneficiado(request, beneficiado_id):
    b = get_object_or_404(Vecino, pk=beneficiado_id)
    try:
        b.delete()
        messages.success(request, 'Vecino eliminado correctamente.')
    except ProtectedError:
        messages.error(request, 'No se puede eliminar porque está vinculado a registros o atenciones sociales.')
    return redirect('administracion:beneficiados')
    
@cargo_required(
    'admin',
    'administrador',
    permission='access_admin_dashboard',
)
def dashboard(request):
    active_delegations = Delegacion.objects.filter(
        Q(estado=Delegacion.Estado.ACTIVADO)
        | Q(estado__iexact='activo'),
    ).count()
    return render(request, 'AdminApp/dashboard.html', {
        'sgr_role': 'Administración',
        'active_user_count': Usuario.objects.filter(is_active=True).count(),
        'active_delegation_count': active_delegations,
        'open_period_count': Periodo.objects.filter(
            estado=Periodo.Estado.ABIERTO,
        ).count(),
        'record_count': Registro.objects.count(),
        'dashboard_modules': _admin_dashboard_modules(request.user),
    })


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
        | Q(
            usuariocargo__fecha_fin__isnull=True,
            usuariocargo__cargo__nombre__iexact='admin',
        )
        | Q(
            usuariocargo__fecha_fin__isnull=True,
            usuariocargo__cargo__nombre__iexact='administrador',
        )
    ).distinct()
    administrator_ids = list(
        active_administrators.values_list('pk', flat=True)[:2]
    )
    last_active_admin_id = (
        administrator_ids[0] if len(administrator_ids) == 1 else None
    )
    status_filter = request.GET.get('estado', '')
    if status_filter not in {'', 'activo', 'inactivo', 'pendiente_activacion'}:
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
        if action not in {'guardar', 'eliminar', 'cambiar_estado', 'reenviar_activacion'}:
            return HttpResponseBadRequest('Acción no válida.')
        target_id = request.POST.get('usuario_id')
        if action == 'reenviar_activacion':
            from config.password_reset import emitir_y_enviar_activacion
            target = get_object_or_404(Usuario, pk=target_id)
            if target.estado != Usuario.EstadoCuenta.PENDIENTE_ACTIVACION:
                messages.warning(request, 'Esta cuenta ya se encuentra activada.')
            else:
                sent = emitir_y_enviar_activacion(target)
                if sent:
                    messages.success(request, f'Se reenvió el enlace de activación a {target.email}.')
                else:
                    messages.warning(request, 'No se pudo enviar el correo de activación. Revisa la configuración SMTP.')
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
                if target_id:
                    messages.success(request, 'La cuenta se actualizó correctamente.')
                else:
                    from config.password_reset import emitir_y_enviar_activacion
                    temp_pwd = getattr(user, '_generated_temp_password', None)
                    enviado = emitir_y_enviar_activacion(user, temp_password=temp_pwd)
                    if enviado:
                        messages.success(
                            request,
                            f'Usuario creado en estado Pendiente de activación. Se envió el enlace y credencial temporal a {user.email}.',
                        )
                    else:
                        messages.warning(
                            request,
                            'Usuario creado en estado Pendiente de activación, pero falló el envío de correo. Usa "Reenviar activación".',
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

    users = Usuario.objects.all()
    query = request.GET.get('q', '').strip()
    if query:
        search = Q()
        for field in (
            'email', 'nombre', 'first_name', 'last_name',
            'usuariocargo__cargo__nombre',
            'usuariodelegacion__delegacion__nombre',
            'usuariorol__rol__nombre',
        ):
            field_filter = {f'{field}__icontains': query}
            if field.startswith('usuariocargo__'):
                field_filter['usuariocargo__fecha_fin__isnull'] = True
            elif field.startswith('usuariodelegacion__'):
                field_filter['usuariodelegacion__fecha_fin__isnull'] = True
            elif field.startswith('usuariorol__'):
                field_filter['usuariorol__fecha_fin__isnull'] = True
            search |= Q(**field_filter)
        users = users.filter(search)
    status = status_filter
    if status == 'activo':
        users = users.filter(is_active=True).exclude(estado=Usuario.EstadoCuenta.PENDIENTE_ACTIVACION)
    elif status == 'pendiente_activacion':
        users = users.filter(estado=Usuario.EstadoCuenta.PENDIENTE_ACTIVACION)
    elif status == 'inactivo':
        users = users.filter(is_active=False)
    delegation_id = delegation_filter
    if delegation_id.isdecimal():
        users = users.filter(
            Q(
                usuariodelegacion__delegacion_id=delegation_id,
                usuariodelegacion__fecha_fin__isnull=True,
            )
        )
    users = users.distinct().order_by('email')
    if request.GET.get('export') == 'excel':
        return excel_response(
            users,
            (
                ('Correo electrónico', 'email'),
                ('Nombre', 'first_name'),
                ('Apellido', 'last_name'),
                ('Cargo', 'cargo'),
                ('Delegación principal', 'delegacion'),
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
        'umbral_rojo': ParametroSistema.Clave.UMBRAL_ROJO,
        'umbral_ambar': ParametroSistema.Clave.UMBRAL_AMBAR,
        'max_dias_autorizacion': ParametroSistema.Clave.MAX_DIAS_AUTORIZACION,
    }
    form = ParametroSistemaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            for field, key in keys.items():
                previous = ParametroSistema.obtener(key)
                parameter, _ = ParametroSistema.objects.get_or_create(
                    clave=key,
                    defaults={
                        'valor': form.cleaned_data[field],
                        'vigente_desde': form.cleaned_data['vigente_desde'],
                    },
                )
                new_value = form.cleaned_data[field]
                new_date = form.cleaned_data['vigente_desde']
                if previous != new_value or parameter.vigente_desde != new_date:
                    parameter.valor = new_value
                    parameter.vigente_desde = new_date
                    parameter.save(update_fields=['valor', 'vigente_desde'])
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

##
## FUNCIONES DE LAS DELEGACIONES
##

def _delegacion_snapshot(delegacion):
    return {
        'nombre': delegacion.nombre,
        'direccion': delegacion.direccion,
        'estado': delegacion.estado,
    }


@cargo_required('admin', 'administrador', permission='access_admin_delegations')
def delegaciones(request):
    """Vista principal para listar, buscar y crear delegaciones en el panel de administración."""
    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').upper()

    queryset = Delegacion.objects.all().order_by('nombre')

    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query) | Q(direccion__icontains=query)
        )

    if estado_filtro:
        if estado_filtro not in {'ACTIVADO', 'DESACTIVADO'}:
            return HttpResponseBadRequest('Filtro de estado no válido.')
        queryset = queryset.filter(estado=estado_filtro)

    form = DelegacionForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                delegacion = form.save()
                registrar_historial(
                    actor=request.user,
                    action='Crear delegación',
                    entity=f'Delegacion:{delegacion.pk}',
                    after=_delegacion_snapshot(delegacion),
                )
            messages.success(request, 'Delegación creada correctamente.')
            return redirect('administracion:delegaciones')
        else:
            messages.error(request, 'Revisa los campos obligatorios del formulario.')

    page_obj = Paginator(queryset, 20).get_page(request.GET.get('page'))

    return render(request, 'AdminApp/delegaciones.html', {
        'sgr_role': 'Administración',
        'sidebar_modules': _admin_dashboard_modules(request.user),
        'form': form,
        'page_obj': page_obj,
        'search_query': query,
        'estado_filtro': estado_filtro,
    })

@cargo_required('admin', 'administrador', permission='view_admin_delegations_detail')
@require_GET
def detalle_delegacion_json(request, delegacion_id):
    """Devuelve los datos reales de la delegación en formato JSON para precargar el modal de edición."""
    delegacion = get_object_or_404(Delegacion, pk=delegacion_id)
    return JsonResponse({
        'id': delegacion.pk,
        'nombre': delegacion.nombre,
        'direccion': delegacion.direccion or '',
        'estado': delegacion.estado,
    })

@cargo_required('admin', 'administrador', permission='edit_admin_delegations_ajax')
@require_POST
def editar_delegacion_ajax(request, delegacion_id):
    """Procesa la actualización de la delegación mediante una petición AJAX asíncrona."""
    delegacion = get_object_or_404(Delegacion, pk=delegacion_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    direccion = data.get('direccion', '').strip() or None
    estado = data.get('estado', 'ACTIVADO').upper()

    if not nombre or not estado:
        return JsonResponse({'success': False, 'message': 'El nombre y el estado son obligatorios.'}, status=400)

    if estado not in {'ACTIVADO', 'DESACTIVADO'}:
        return JsonResponse({'success': False, 'message': 'Estado no válido. Debe ser ACTIVADO o DESACTIVADO.'}, status=400)
    
    if Delegacion.objects.filter(nombre__iexact=nombre).exclude(pk=delegacion.pk).exists():
        return JsonResponse({'success': False, 'message': f'Ya existe otra delegación con el nombre "{nombre}".'}, status=400)
    
    before = _delegacion_snapshot(delegacion)
    try:
        with transaction.atomic():
            delegacion.nombre = nombre
            delegacion.direccion = direccion
            delegacion.estado = estado
            delegacion.save()

            registrar_historial(
                actor=request.user,
                action='Editar delegación AJAX',
                entity=f'Delegacion:{delegacion.pk}',
                before=before,
                after=_delegacion_snapshot(delegacion),
            )
        return JsonResponse({'success': True, 'message': 'La delegación fue actualizada correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar la delegación: {str(e)}'}, status=500)


@cargo_required('admin', 'administrador', permission='edit_admin_delegations_ajax')
@require_POST
def cambiar_estado_delegacion_ajax(request, delegacion_id):
    """Alterna el estado lógico de la delegación (ACTIVADO <-> DESACTIVADO) vía AJAX y registra en Historial."""
    delegacion = get_object_or_404(Delegacion, pk=delegacion_id)
    before = _delegacion_snapshot(delegacion)

    nuevo_estado = (Delegacion.Estado.DESACTIVADO
        if delegacion.estado == Delegacion.Estado.ACTIVADO
        else Delegacion.Estado.ACTIVADO
    )
    accion_texto = 'Desactivar delegación' if nuevo_estado == Delegacion.Estado.DESACTIVADO else 'Activar delegación'

    try:
        with transaction.atomic():
            delegacion.estado = nuevo_estado
            delegacion.save(update_fields=['estado'])

            registrar_historial(
                actor=request.user,
                action=accion_texto,
                entity=f'Delegacion:{delegacion.pk}',
                before=before,
                after=_delegacion_snapshot(delegacion),
            )
        etiqueta = 'Activada' if nuevo_estado == Delegacion.Estado.ACTIVADO else 'Desactivada'
        return JsonResponse({
            'success': True,
            'estado': nuevo_estado,
            'message': f'La delegación "{delegacion.nombre}" pasó a estado {etiqueta} y se registró en auditoría.',
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error al cambiar el estado de la delegación: {str(e)}',
        }, status=500)


@cargo_required('admin', 'administrador', permission='access_admin_delegations')
@require_GET
def buscar_delegaciones_ajax(request):
    """Endpoint AJAX (keyup) para filtrar delegaciones dinámicamente sin recargar."""
    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').upper()

    queryset = Delegacion.objects.all().order_by('nombre')
    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query) | Q(direccion__icontains=query)
        )
    if estado_filtro in {'ACTIVADO', 'DESACTIVADO'}:
        queryset = queryset.filter(estado=estado_filtro)

    resultados = [
        {
            'id': d.pk,
            'nombre': d.nombre,
            'direccion': d.direccion or '',
            'estado': d.estado,
        }
        for d in queryset[:50]
    ]
    return JsonResponse({'success': True, 'delegaciones': resultados})


@cargo_required('admin', 'administrador', permission='access_admin_positions')
def cargos(request):
    return maintainer(request, 'cargos')


@cargo_required('admin', 'administrador', permission='access_admin_functions')
def funciones(request):
    return maintainer(request, 'funciones')


@cargo_required('admin', 'administrador', permission='access_admin_position_functions')
def cargos_funciones(request):
    return maintainer(request, 'cargos-funciones')


@cargo_required('admin', 'administrador', permission='access_admin_roles')
def roles(request):
    return maintainer(request, 'roles')

##
## FUNCIONES DE LOS ÍTEMS
##

def _item_snapshot(item):
    return {
        'codigo': item.codigo or '',
        'nombre': item.nombre,
        'descripcion': item.descripcion or '',
        'estado': item.estado,
    }


@cargo_required('coordinador', 'admin', 'administrador', permission='access_admin_items')
def items(request):
    """Vista principal para listar, buscar y crear ítems en el panel de administración."""
    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').lower()

    queryset = Item.objects.all().order_by('nombre')

    if query:
        queryset = queryset.filter(
            Q(codigo__icontains=query)
            | Q(nombre__icontains=query)
            | Q(descripcion__icontains=query)
        )

    if estado_filtro:
        if estado_filtro not in {'activo', 'inactivo'}:
            return HttpResponseBadRequest('Filtro de estado no válido.')
        queryset = queryset.filter(estado=estado_filtro)

    form = ItemForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                item = form.save()
                registrar_historial(
                    actor=request.user,
                    action='Crear ítem',
                    entity=f'Item:{item.pk}',
                    after=_item_snapshot(item),
                )
            messages.success(request, f'Ítem "{item.nombre}" ({item.codigo}) creado correctamente.')
            return redirect('administracion:items')
        else:
            errores = '; '.join(
                f"{campo}: {', '.join(msgs)}" for campo, msgs in form.errors.items()
            )
            messages.error(request, f'Error al registrar el ítem: {errores}')

    page_obj = Paginator(queryset, 20).get_page(request.GET.get('page'))

    return render(request, 'AdminApp/items.html', {
        'sgr_role': 'Administración',
        'sidebar_modules': _admin_dashboard_modules(request.user),
        'form': form,
        'page_obj': page_obj,
        'search_query': query,
        'estado_filtro': estado_filtro,
    })


@cargo_required('coordinador', 'admin', 'administrador', permission='search_admin_items_ajax')
@require_GET
def buscar_items_ajax(request):
    """Endpoint AJAX (keyup) para filtrar ítems dinámicamente sin recargar la página."""
    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').lower()

    queryset = Item.objects.all().order_by('nombre')

    if query:
        queryset = queryset.filter(
            Q(codigo__icontains=query)
            | Q(nombre__icontains=query)
            | Q(descripcion__icontains=query)
        )

    if estado_filtro in {'activo', 'inactivo'}:
        queryset = queryset.filter(estado=estado_filtro)

    resultados = [
        {
            'id': item.pk,
            'codigo': item.codigo or 'S/C',
            'nombre': item.nombre,
            'descripcion': item.descripcion or '',
            'estado': item.estado,
            'estado_display': item.get_estado_display(),
        }
        for item in queryset[:50]
    ]
    return JsonResponse({'success': True, 'items': resultados})


@cargo_required('coordinador', 'admin', 'administrador', permission='view_admin_items_detail')
@require_GET
def detalle_item_json(request, item_id):
    """Devuelve los datos del ítem en formato JSON para precargar el modal de edición."""
    item = get_object_or_404(Item, pk=item_id)
    return JsonResponse({
        'id': item.pk,
        'codigo': item.codigo or '',
        'nombre': item.nombre,
        'descripcion': item.descripcion or '',
        'estado': item.estado,
    })


@cargo_required('coordinador', 'admin', 'administrador', permission='edit_admin_items_ajax')
@require_POST
def editar_item_ajax(request, item_id):
    """Procesa la actualización del ítem mediante AJAX y registra el cambio en Historial."""
    item = get_object_or_404(Item, pk=item_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    descripcion = data.get('descripcion', '').strip()
    estado = data.get('estado', 'activo').lower()

    if not nombre:
        return JsonResponse({'success': False, 'message': 'El nombre del ítem es obligatorio.'}, status=400)

    if len(nombre) > 120:
        return JsonResponse({'success': False, 'message': 'El nombre no puede superar los 120 caracteres.'}, status=400)

    if estado not in {'activo', 'inactivo'}:
        return JsonResponse({'success': False, 'message': 'Estado no válido. Debe ser Activo o Inactivo.'}, status=400)

    if Item.objects.filter(nombre__iexact=nombre).exclude(pk=item.pk).exists():
        return JsonResponse({'success': False, 'message': f'Ya existe otro ítem registrado con el nombre "{nombre}".'}, status=400)

    before = _item_snapshot(item)
    try:
        with transaction.atomic():
            item.nombre = nombre
            item.descripcion = descripcion
            item.estado = estado
            item.save()

            registrar_historial(
                actor=request.user,
                action='Editar ítem',
                entity=f'Item:{item.pk}',
                before=before,
                after=_item_snapshot(item),
            )
        return JsonResponse({'success': True, 'message': 'El ítem fue actualizado correctamente y registrado en auditoría.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error interno al actualizar el ítem: {str(e)}'}, status=500)


@cargo_required('coordinador', 'admin', 'administrador', permission='toggle_admin_items_status')
@require_POST
def cambiar_estado_item_ajax(request, item_id):
    """Alterna el estado lógico del ítem (activo <-> inactivo) vía AJAX y registra en Historial."""
    item = get_object_or_404(Item, pk=item_id)
    before = _item_snapshot(item)

    nuevo_estado = (Item.Estado.INACTIVO if item.estado == Item.Estado.ACTIVO else Item.Estado.ACTIVO)
    accion_texto = 'Desactivar ítem' if nuevo_estado == Item.Estado.INACTIVO else 'Activar ítem'

    try:
        with transaction.atomic():
            item.estado = nuevo_estado
            item.save(update_fields=['estado'])

            registrar_historial(
                actor=request.user,
                action=accion_texto,
                entity=f'Item:{item.pk}',
                before=before,
                after=_item_snapshot(item),
            )
        estado_etiqueta = 'Activado' if nuevo_estado == Item.Estado.ACTIVO else 'Desactivado'
        return JsonResponse({
            'success': True,
            'estado': nuevo_estado,
            'message': f'El ítem "{item.nombre}" pasó a estado {estado_etiqueta} y se registró en auditoría.',
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error al cambiar el estado del ítem: {str(e)}',
        }, status=500)



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
        'periodo', 'vecino', 'aprobador',
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
        page_obj = Paginator(Historial.objects.none(), 25).get_page(request.GET.get('page'))
        return render(request, 'AdminApp/audit_viewer.html', {
            'sgr_role': 'AdministraciÃ³n',
            'page_title': 'Historial del sistema',
            'columns': ('Fecha', 'AcciÃ³n', 'Entidad', 'Autor', 'PerÃ­odo', 'Valor anterior', 'Valor nuevo'),
            'rows': [],
            'filter_form': form,
            'page_obj': page_obj,
            'pagination_query': _audit_pagination_query(request),
            'result_count': 0,
            'route_name': 'administracion:historial',
        })

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
    if form.cleaned_data['entidad']:
        entries = entries.filter(entidad_afectada__icontains=form.cleaned_data['entidad'])
    if form.cleaned_data['usuario']:
        entries = entries.filter(autor=form.cleaned_data['usuario'])
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
        page_obj = Paginator(PasswordResetAuditEvent.objects.none(), 25).get_page(request.GET.get('page'))
        return render(request, 'AdminApp/audit_viewer.html', {
            'sgr_role': 'Administración',
            'page_title': 'Auditoría de recuperación de contraseña',
            'columns': ('Fecha', 'Evento', 'Usuario', 'Dirección IP', 'Límite aplicado'),
            'rows': [],
            'filter_form': form,
            'page_obj': page_obj,
            'pagination_query': _audit_pagination_query(request),
            'result_count': 0,
            'route_name': 'administracion:auditoria-recuperacion',
        })

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



@cargo_required('admin', 'administrador', permission='access_admin_beneficiados')
def beneficiados_vista(request):
    """Vista principal para consultar y listar vecinos en el panel de administración."""
    query = request.GET.get('q', '').strip()
    queryset = Vecino.objects.all().order_by('nombre')
    
    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query)
            | Q(rut__icontains=query)
            | Q(email__icontains=query)
            | Q(telefono__icontains=query)
        )

    return render(request, 'AdminApp/beneficiados.html', {
        'sgr_role': 'Administración',
        'dashboard_modules': _admin_dashboard_modules(request.user),
        'beneficiados': queryset[:50],  # Mantén la variable 'beneficiados' si tu template HTML la espera con ese nombre
        'query': query,
    })






