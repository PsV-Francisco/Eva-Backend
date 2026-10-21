from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from AdminApp.forms import (
    ParametroSistemaForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from AdminApp.models import Cargo, Delegacion, ParametroSistema, Usuario
from AdminApp.maintainers import excel_response, maintainer
from config.decorators import cargo_required


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


@cargo_required('admin', 'administrador')
def home(request):
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
                except ProtectedError:
                    messages.error(request, 'No se puede eliminar esta cuenta porque tiene información asociada.')
            return redirect('administracion:home')

        if action == 'cambiar_estado':
            target = get_object_or_404(Usuario, pk=target_id)
            if target.pk == request.user.pk or target.is_superuser:
                messages.error(request, 'No puedes desactivar tu propia cuenta ni otra cuenta superadministradora.')
            else:
                before = _user_snapshot(target)
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
            return redirect('administracion:home')

        if target_id:
            editing_user = get_object_or_404(Usuario, pk=target_id)
            form = UsuarioUpdateForm(request.POST, instance=editing_user)
        else:
            form = UsuarioCreationForm(request.POST)

        before = _user_snapshot(editing_user) if target_id else None
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                registrar_historial(
                    actor=request.user,
                    action='Editar usuario' if target_id else 'Crear usuario',
                    entity=f'Usuario:{user.pk}',
                    before=before,
                    after=_user_snapshot(user),
                )
            messages.success(
                request,
                'La cuenta se actualizó correctamente.' if target_id
                else 'El usuario quedó creado correctamente.',
            )
            return redirect('administracion:home')
        messages.error(request, 'Revisa los campos del formulario.')
    else:
        form = (
            UsuarioUpdateForm(instance=editing_user)
            if editing_user else UsuarioCreationForm()
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


@cargo_required('admin', 'administrador')
def parametros(request):
    keys = {
        'tope_cumplimiento': ParametroSistema.Clave.TOPE_CUMPLIMIENTO,
        'umbral_delegacion': ParametroSistema.Clave.UMBRAL_DELEGACION,
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


@cargo_required('admin', 'administrador')
def delegaciones(request):
    return maintainer(request, 'delegaciones')


@cargo_required('admin', 'administrador')
def roles(request):
    return maintainer(request, 'roles')


@cargo_required('coordinador', 'admin', 'administrador')
def items(request):
    return maintainer(request, 'items')


@cargo_required('admin', 'administrador')
def tipos_atencion(request):
    return maintainer(request, 'tipos-atencion')


@cargo_required('admin', 'administrador')
def subatenciones(request):
    return maintainer(request, 'subatenciones')


@cargo_required('coordinador', 'admin', 'administrador')
def metas(request):
    return maintainer(request, 'metas')
