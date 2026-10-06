from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from config.decorators import cargo_required
from CoordinadorApp.models import Periodo
from DelegadoApp.forms import CompromisoEstadoForm, CompromisoForm
from DelegadoApp.models import Agenda, Compromiso


@cargo_required('delegado')
def home(request):
    delegation_id = request.user.delegacion_id
    commitments = Compromiso.objects.none()
    if delegation_id:
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
        ).select_related('agenda', 'agenda__periodo').prefetch_related('responsables')

    if request.method == 'POST' and request.POST.get('action') == 'estado':
        if not delegation_id:
            messages.error(request, 'Tu cuenta no tiene una delegación asignada.')
        else:
            compromiso = get_object_or_404(commitments, pk=request.POST.get('compromiso_id'))
            state_form = CompromisoEstadoForm(request.POST)
            if state_form.is_valid():
                compromiso.estado = state_form.cleaned_data['estado']
                compromiso.save(update_fields=['estado'])
                messages.success(request, 'El estado del compromiso quedó actualizado.')
            else:
                messages.error(request, 'Selecciona un estado válido.')
        return redirect('delegado:home')

    form = CompromisoForm(request.POST or None, user=request.user)
    if request.method == 'POST':
        if not delegation_id:
            messages.error(request, 'Asigna una delegación a tu cuenta antes de crear compromisos.')
        elif form.is_valid():
            period = form.cleaned_data['periodo']
            agenda, _ = Agenda.objects.get_or_create(
                delegacion_id=delegation_id, periodo=period,
            )
            commitment = form.save(commit=False)
            commitment.agenda = agenda
            commitment.save()
            form.save_m2m()
            messages.success(request, 'El compromiso quedó agregado a la agenda.')
            return redirect('delegado:home')
        else:
            messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')

    return render(request, 'DelegadoApp/index.html', {
        'sgr_role': 'Delegación', 'form': form, 'commitments': commitments[:30],
        'commitment_count': commitments.count(), 'has_delegation': bool(delegation_id),
    })
