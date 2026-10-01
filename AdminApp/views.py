from django.contrib import messages
from django.shortcuts import redirect, render

from AdminApp.forms import UsuarioCreationForm
from AdminApp.models import Cargo, Delegacion, Usuario
from config.decorators import role_required


@role_required('admin', 'administrador', allow_staff=True)
def home(request):
    form = UsuarioCreationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'El usuario quedó creado correctamente.')
            return redirect('administracion:home')
        messages.error(request, 'Revisa los campos del formulario.')

    context = {
        'sgr_role': 'Administración',
        'form': form,
        'users': Usuario.objects.select_related('delegacion', 'cargo').prefetch_related('roles').order_by('email')[:12],
        'user_count': Usuario.objects.count(),
        'delegation_count': Delegacion.objects.count(),
        'position_count': Cargo.objects.count(),
    }
    return render(request, 'AdminApp/index.html', context)
