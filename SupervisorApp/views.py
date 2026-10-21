from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from CoordinadorApp.models import Periodo
from config.decorators import cargo_required
from FuncionarioApp.models import Registro
from SupervisorApp.forms import RevisionEvidenciaForm
from SupervisorApp.models import Evidencia, RevisionEvidencia


def _evidencias_visibles(user):
    evidences = Evidencia.objects.select_related(
        'registro', 'compromiso', 'supervisor',
        'gestion_atencion', 'gestion_atencion__atencion',
    )
    if user.is_superuser:
        return evidences
    if not user.delegacion_id:
        return evidences.none()
    return evidences.filter(
        Q(registro__autor__delegacion_id=user.delegacion_id)
        | Q(compromiso__agenda__delegacion_id=user.delegacion_id)
        | Q(gestion_atencion__atencion__usuario__delegacion_id=user.delegacion_id)
    )


def _evidence_period(evidencia):
    if evidencia.registro_id:
        return evidencia.registro.periodo
    if evidencia.compromiso_id:
        return evidencia.compromiso.agenda.periodo
    return None


@cargo_required('supervisor', 'verificador')
def home(request):
    if request.method == 'POST':
        evidencia = get_object_or_404(
            _evidencias_visibles(request.user),
            pk=request.POST.get('evidencia_id'),
        )
        form = RevisionEvidenciaForm(request.POST)
        period = _evidence_period(evidencia)
        if period and period.estado != Periodo.Estado.ABIERTO:
            messages.error(request, 'Las evidencias de un período cerrado son de solo lectura.')
        elif evidencia.estado != Evidencia.Estado.PENDIENTE:
            messages.error(request, 'Esta evidencia ya fue revisada.')
        elif form.is_valid():
            with transaction.atomic():
                revision = form.save(commit=False)
                revision.evidencia = evidencia
                revision.verificador = request.user
                revision.save()
                previous = {'estado': evidencia.estado}
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
                registrar_historial(
                    actor=request.user,
                    action='Validar evidencia',
                    entity=f'Evidencia:{evidencia.pk}',
                    before=previous,
                    after={
                        'estado': evidencia.estado,
                        'decision': revision.decision,
                        'observaciones': revision.observaciones,
                        'codigo': str(evidencia.codigo),
                    },
                    period=period,
                )
            messages.success(request, 'La revisión quedó registrada.')
        else:
            messages.error(request, 'Selecciona una decisión válida y revisa la observación.')
        return redirect('supervisor:home')

    evidencias = _evidencias_visibles(request.user).filter(
        estado=Evidencia.Estado.PENDIENTE,
    ).filter(
        Q(registro__isnull=True)
        | Q(registro__periodo__estado=Periodo.Estado.ABIERTO)
    ).filter(
        Q(compromiso__isnull=True)
        | Q(compromiso__agenda__periodo__estado=Periodo.Estado.ABIERTO)
    )
    return render(request, 'SupervisorApp/index.html', {
        'sgr_role': 'Verificación', 'evidencias': evidencias,
        'pending_count': evidencias.count(), 'review_form': RevisionEvidenciaForm(),
        'revisiones': RevisionEvidencia.objects.filter(
            verificador=request.user,
        ).select_related(
            'evidencia', 'evidencia__registro', 'evidencia__compromiso',
        )[:20],
        'sidebar_modules': (
            {'label': 'Validar evidencias', 'url_name': 'supervisor:home'},
        ),
    })
