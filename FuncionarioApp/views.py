from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from config.decorators import cargo_required
from FuncionarioApp.forms import RegistroForm
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


@cargo_required('funcionario')
def home(request):
    form = RegistroForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                registro = form.save(commit=False)
                registro.autor = request.user
                registro.save()
                uploaded_file = form.cleaned_data.get('evidencia')
                if uploaded_file:
                    Evidencia.objects.create(archivo=uploaded_file, registro=registro)
            messages.success(request, f'Actividad registrada con código {registro.codigo}.')
            return redirect('funcionario:home')
        messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')

    registros = Registro.objects.filter(autor=request.user).select_related('item', 'periodo')
    return render(request, 'FuncionarioApp/index.html', {
        'sgr_role': 'Funcionario', 'form': form, 'registros': registros[:20],
        'registro_count': registros.count(),
    })
