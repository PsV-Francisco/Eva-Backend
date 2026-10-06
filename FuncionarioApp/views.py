from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from config.decorators import cargo_required
from FuncionarioApp.forms import RegistroForm
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


@cargo_required('funcionario')
def home(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        registro_id = request.POST.get('registro_id')
        if registro_id:
            registro = get_object_or_404(
                Registro, pk=registro_id, autor=request.user,
                estado=Registro.Estado.PENDIENTE,
            )
            if action == 'eliminar' and registro.evidencias_registros.exists():
                messages.error(request, 'No se puede eliminar una actividad que ya tiene evidencias asociadas.')
                return redirect('funcionario:home')
        else:
            registro = None

        if action == 'eliminar':
            if registro is None:
                messages.error(request, 'No se encontró la actividad que intentas eliminar.')
            else:
                registro.delete()
                messages.success(request, 'La actividad se eliminó correctamente.')
            return redirect('funcionario:home')

        form = RegistroForm(
            request.POST, request.FILES or None, instance=registro, user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                registro = form.save(commit=False)
                registro.autor = request.user
                registro.save()
                uploaded_file = form.cleaned_data.get('evidencia')
                if uploaded_file:
                    Evidencia.objects.create(archivo=uploaded_file, registro=registro)
            messages.success(
                request,
                f'Actividad actualizada: {registro.codigo}' if registro_id
                else f'Actividad registrada con código {registro.codigo}.',
            )
            return redirect('funcionario:home')
        messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    else:
        edit_id = request.GET.get('editar')
        registro = get_object_or_404(
            Registro, pk=edit_id, autor=request.user,
            estado=Registro.Estado.PENDIENTE,
        ) if edit_id else None
        form = RegistroForm(instance=registro, user=request.user)

    registros = Registro.objects.filter(autor=request.user).select_related('item', 'periodo')
    return render(request, 'FuncionarioApp/index.html', {
        'sgr_role': 'Funcionario', 'form': form, 'registros': registros[:20],
        'editing_record': registro,
        'sidebar_modules': (
            'Registro de Actividades', 'Atención Social',
            'Agenda Colectiva', 'Cumplimiento',
        ),
        'registro_count': registros.count(),
    })
