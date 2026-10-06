from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from config.decorators import cargo_required
from CoordinadorApp.forms import PeriodoForm
from CoordinadorApp.models import Desempeno, Periodo


@cargo_required('coordinador')
def home(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        periodo_id = request.POST.get('periodo_id')
        if action == 'eliminar':
            periodo = get_object_or_404(Periodo, pk=periodo_id)
            try:
                periodo.delete()
                messages.success(request, 'El período se eliminó correctamente.')
            except ProtectedError:
                messages.error(request, 'No se puede eliminar un período asociado a actividades o mediciones.')
            return redirect('coordinador:home')

        instance = get_object_or_404(Periodo, pk=periodo_id) if periodo_id else None
        form = PeriodoForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                'El período se actualizó correctamente.' if instance
                else 'El período quedó configurado.',
            )
            return redirect('coordinador:home')
        messages.error(request, 'No se pudo guardar el período. Revisa las fechas y los campos.')
    else:
        edit_id = request.GET.get('editar')
        instance = get_object_or_404(Periodo, pk=edit_id) if edit_id else None
        form = PeriodoForm(instance=instance)

    periodos = Periodo.objects.all()
    return render(request, 'CoordinadorApp/index.html', {
        'sgr_role': 'Coordinación', 'form': form, 'periodos': periodos,
        'editing_period': instance,
        'sidebar_modules': (
            'Metas e indicadores', 'Avance esperado', 'Informes de gestión',
            'Tendencias históricas', 'Actividades', 'Gestión de periodos',
        ),
        'periodo_count': periodos.count(), 'periodos_abiertos': periodos.filter(estado=Periodo.Estado.ABIERTO).count(),
        'desempeno_count': Desempeno.objects.count(),
    })
