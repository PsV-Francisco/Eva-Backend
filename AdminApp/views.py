from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.forms import UsuarioCreationForm, UsuarioUpdateForm
from AdminApp.models import Cargo, Delegacion, Usuario
from config.decorators import cargo_required


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
                    target.delete()
                    messages.success(request, 'La cuenta se eliminó correctamente.')
                except ProtectedError:
                    messages.error(request, 'No se puede eliminar esta cuenta porque tiene información asociada.')
            return redirect('administracion:home')

        if target_id:
            editing_user = get_object_or_404(Usuario, pk=target_id)
            form = UsuarioUpdateForm(request.POST, instance=editing_user)
        else:
            form = UsuarioCreationForm(request.POST)

        if form.is_valid():
            form.save()
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
        ),
        'users': Usuario.objects.select_related('delegacion', 'cargo').prefetch_related('roles').order_by('email')[:12],
        'user_count': Usuario.objects.count(),
        'delegation_count': Delegacion.objects.count(),
        'position_count': Cargo.objects.count(),
    }
    return render(request, 'AdminApp/index.html', context)
