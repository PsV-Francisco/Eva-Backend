from django.contrib import messages
from django.shortcuts import redirect, render

from config.decorators import role_required
from CoordinadorApp.forms import PeriodoForm
from CoordinadorApp.models import Desempeno, Periodo


@role_required('coordinador')
def home(request):
    form = PeriodoForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'El período quedó configurado.')
            return redirect('coordinador:home')
        messages.error(request, 'No se pudo guardar el período. Revisa las fechas y los campos.')

    periodos = Periodo.objects.all()
    return render(request, 'CoordinadorApp/index.html', {
        'sgr_role': 'Coordinación', 'form': form, 'periodos': periodos,
        'periodo_count': periodos.count(), 'periodos_abiertos': periodos.filter(estado=Periodo.Estado.ABIERTO).count(),
        'desempeno_count': Desempeno.objects.count(),
    })
