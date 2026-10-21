from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from AdminApp.forms import (
    ParametroSistemaForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from AdminApp.models import Cargo, Delegacion, ParametroSistema, Usuario
from config.decorators import cargo_required


def _user_snapshot(user):
    return {
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'delegacion_id': user.delegacion_id,
        'cargo_id': user.cargo_id,
        'roles': list(user.roles.order_by('pk').values_list('pk', flat=True)),
        'is_active': user.is_active,
    }


@cargo_required('admin', 'administrador')
def home(request):
    edit_id = request.GET.get('editar')
    editing_user = None
    if edit_id:
        editing_user = get_object_or_404(Usuario, pk=edit_id)

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
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

    context = {
        'sgr_role': 'Administración',
        'form': form,
        'editing_user': editing_user,
        'sidebar_modules': (
            'Gestión de la medición', 'Gestión de las delegaciones',
            'Gestión de catálogos', 'Consulta del historial',
            {'label': 'Parámetros del sistema', 'url_name': 'administracion:parametros'},
        ),
        'users': Usuario.objects.select_related('delegacion', 'cargo').prefetch_related('roles').order_by('email')[:12],
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
