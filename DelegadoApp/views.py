from django.contrib import messages
from django.db.models.deletion import ProtectedError
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
        ).select_related('agenda', 'agenda__periodo').prefetch_related(
            'responsables', 'evidencias_compromiso',
        )

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

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        compromiso_id = request.POST.get('compromiso_id')
        if compromiso_id:
            commitment = get_object_or_404(commitments, pk=compromiso_id)
        else:
            commitment = None

        if action == 'eliminar':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas eliminar.')
            elif commitment.evidencias_compromiso.exists():
                messages.error(request, 'No se puede eliminar un compromiso con evidencias asociadas.')
            else:
                try:
                    commitment.delete()
                    messages.success(request, 'El compromiso se eliminó correctamente.')
                except ProtectedError:
                    messages.error(request, 'No se puede eliminar un compromiso que tiene información asociada.')
            return redirect('delegado:home')

        if commitment and commitment.evidencias_compromiso.exists():
            messages.error(request, 'No se puede modificar un compromiso con evidencias asociadas.')
            return redirect('delegado:home')

        if not delegation_id:
            messages.error(request, 'Asigna una delegación a tu cuenta antes de crear compromisos.')
            return redirect('delegado:home')

        form = CompromisoForm(
            request.POST, user=request.user, instance=commitment,
        )
        if form.is_valid():
            period = form.cleaned_data['periodo']
            agenda, _ = Agenda.objects.get_or_create(
                delegacion_id=delegation_id, periodo=period,
            )
            commitment = form.save(commit=False)
            commitment.agenda = agenda
            commitment.save()
            form.save_m2m()
            messages.success(
                request,
                'El compromiso se actualizó correctamente.' if compromiso_id
                else 'El compromiso quedó agregado a la agenda.',
            )
            return redirect('delegado:home')
        else:
            messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    else:
        edit_id = request.GET.get('editar')
        commitment = get_object_or_404(commitments, pk=edit_id) if edit_id else None
        form = CompromisoForm(instance=commitment, user=request.user)

    return render(request, 'DelegadoApp/index.html', {
        'sgr_role': 'Delegación', 'form': form, 'commitments': commitments[:30],
        'commitment_count': commitments.count(), 'has_delegation': bool(delegation_id),
        'editing_commitment': commitment,
        'sidebar_modules': (
            'Cumplimiento de delegación', 'Agenda colectiva',
            'Resumen de la delegación',
        ),
    })
