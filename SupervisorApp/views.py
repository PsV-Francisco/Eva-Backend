from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from config.decorators import cargo_required
from FuncionarioApp.models import Registro
from SupervisorApp.forms import RevisionEvidenciaForm
from SupervisorApp.models import Evidencia, RevisionEvidencia


@cargo_required('supervisor', 'verificador')
def home(request):
    if request.method == 'POST':
        evidencia = get_object_or_404(Evidencia, pk=request.POST.get('evidencia_id'))
        form = RevisionEvidenciaForm(request.POST)
        if evidencia.estado != Evidencia.Estado.PENDIENTE:
            messages.error(request, 'Esta evidencia ya fue revisada.')
        elif form.is_valid():
            with transaction.atomic():
                revision = form.save(commit=False)
                revision.evidencia = evidencia
                revision.verificador = request.user
                revision.save()
                if revision.decision in (RevisionEvidencia.Decision.APROBADA, RevisionEvidencia.Decision.RECHAZADA):
                    evidencia.estado = revision.decision
                    evidencia.save(update_fields=['estado'])
                    if evidencia.registro_id:
                        evidencia.registro.estado = (
                            Registro.Estado.VALIDADA
                            if revision.decision == RevisionEvidencia.Decision.APROBADA
                            else Registro.Estado.OBSERVADA
                        )
                        evidencia.registro.save(update_fields=['estado'])
            messages.success(request, 'La revisión quedó registrada.')
        else:
            messages.error(request, 'Selecciona una decisión válida y revisa la observación.')
        return redirect('supervisor:home')

    evidencias = Evidencia.objects.filter(estado=Evidencia.Estado.PENDIENTE).select_related(
        'registro', 'compromiso', 'supervisor',
    )
    if request.user.delegacion_id:
        evidencias = evidencias.filter(
            Q(registro__autor__delegacion_id=request.user.delegacion_id)
            | Q(compromiso__agenda__delegacion_id=request.user.delegacion_id)
        )
    elif not request.user.is_superuser:
        evidencias = Evidencia.objects.none()
    return render(request, 'SupervisorApp/index.html', {
        'sgr_role': 'Verificación', 'evidencias': evidencias,
        'pending_count': evidencias.count(), 'review_form': RevisionEvidenciaForm(),
        'revisiones': RevisionEvidencia.objects.filter(
            verificador=request.user,
        ).select_related(
            'evidencia', 'evidencia__registro', 'evidencia__compromiso',
        )[:20],
        'sidebar_modules': (
            'Revisión de Compromisos', 'Revisión de Actividades',
            'Funciones e Indicadores',
        ),
    })
