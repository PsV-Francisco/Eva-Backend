from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from CoordinadorApp.models import Periodo
from config.decorators import cargo_required
from config.permissions import ids_cargos_funcionario
from CoordinadorApp.services import periodo_vigente
from config.delegations import active_delegation
from FuncionarioApp.models import Registro
from SupervisorApp.forms import RevisionEvidenciaForm
from SupervisorApp.models import Evidencia, ObservacionRegistro, RevisionEvidencia
from DelegadoApp.services import actividad_reciente
from AdminApp.pagination_utils import paginate_queryset


def _evidencias_visibles(request):
    user = request.user
    delegation = active_delegation(request)
    evidences = Evidencia.objects.prefetch_related(
        'registros__autor',
        'registros__item',
        'registros__periodo',
        'compromisos__agenda__periodo',
        'atenciones_sociales__autor',
        'atenciones_sociales__gestion_atencion',
    )
    if delegation:
        delegation_id = delegation.pk
    elif user.is_superuser:
        return evidences
    else:
        return evidences.none()

    return evidences.filter(
        Q(
            registros__autor__usuariodelegacion__delegacion_id=delegation_id,
            registros__autor__usuariodelegacion__fecha_fin__isnull=True,
        )
        | Q(compromisos__agenda__delegacion_id=delegation_id)
        | Q(
            atenciones_sociales__autor__usuariodelegacion__delegacion_id=delegation_id,
            atenciones_sociales__autor__usuariodelegacion__fecha_fin__isnull=True,
        )
    ).distinct()


def _evidence_origin(evidencia):
    registro = evidencia.registros.first()
    compromiso = evidencia.compromisos.first()
    atencion = evidencia.atenciones_sociales.first()
    return registro, compromiso, atencion


def _evidence_period(evidencia):
    registro, compromiso, _ = _evidence_origin(evidencia)
    if registro:
        return registro.periodo
    if compromiso:
        return compromiso.agenda.periodo
    return None


@cargo_required('supervisor', 'verificador', permission='review_evidence')
def home(request):
    if request.method == 'POST':
        evidencia = get_object_or_404(
            _evidencias_visibles(request),
            pk=request.POST.get('evidencia_id'),
        )
        form = RevisionEvidenciaForm(request.POST)
        period = _evidence_period(evidencia)
        registro, compromiso, _ = _evidence_origin(evidencia)

        if period and (period.estado or '').strip().casefold() != Periodo.Estado.ABIERTO:
            messages.error(request, 'Las evidencias de un período cerrado son de solo lectura.')
        elif (evidencia.estado or '').strip().casefold() != Evidencia.Estado.PENDIENTE:
            messages.error(request, 'Esta evidencia ya fue revisada.')
        elif form.is_valid():
            with transaction.atomic():
                revision = form.save(commit=False)
                revision.evidencia = evidencia
                revision.verificador = request.user
                revision.save()
                if revision.observaciones.strip() and registro:
                    ObservacionRegistro.objects.create(
                        registro=registro,
                        evidencia=evidencia,
                        autor=request.user,
                        comentario=revision.observaciones.strip(),
                    )

                previous = {
                    'estado': evidencia.estado,
                    'genera_puntaje': registro.genera_puntaje if registro else None,
                }
                decision = revision.decision

                if decision in (
                    RevisionEvidencia.Decision.APROBADA,
                    RevisionEvidencia.Decision.APROBADA_NO_PONDERA,
                ):
                    pondera = decision == RevisionEvidencia.Decision.APROBADA
                    evidencia.estado = Evidencia.Estado.APROBADA
                    evidencia.save(update_fields=['estado'])

                    if registro:
                        registro.estado = Registro.Estado.VALIDADA
                        registro.genera_puntaje = 'SI' if pondera else 'NO'
                        registro.save(update_fields=['estado', 'genera_puntaje'])
                    if compromiso:
                        compromiso.genera_puntaje = Decimal('1.0') if pondera else Decimal('0.0')
                        compromiso.save(update_fields=['genera_puntaje'])

                elif decision == RevisionEvidencia.Decision.RECHAZADA:
                    evidencia.estado = Evidencia.Estado.RECHAZADA
                    evidencia.save(update_fields=['estado'])
                    if registro:
                        registro.estado = Registro.Estado.OBSERVADA
                        registro.genera_puntaje = 'NO'
                        registro.save(update_fields=['estado', 'genera_puntaje'])

                elif decision == RevisionEvidencia.Decision.CORRECCION:
                    # Mantiene la evidencia pendiente para que el funcionario complemente
                    if registro:
                        registro.estado = Registro.Estado.OBSERVADA
                        registro.save(update_fields=['estado'])

                registrar_historial(
                    actor=request.user,
                    action='Validar evidencia',
                    entity=f'Evidencia:{evidencia.pk}',
                    before=previous,
                    after={
                        'estado': evidencia.estado,
                        'decision': revision.decision,
                        'observaciones': revision.observaciones,
                        'genera_puntaje': registro.genera_puntaje if registro else None,
                        'codigo': str(evidencia.codigo),
                    },
                    period=period,
                )
            messages.success(request, 'La revisión y decisión de ponderación quedaron registradas.')
        else:
            messages.error(request, 'Selecciona una decisión válida y revisa la observación.')
        return redirect('supervisor:home')

    evidencias = _evidencias_visibles(request).filter(
        estado=Evidencia.Estado.PENDIENTE,
    ).filter(
        Q(registros__isnull=True)
        | Q(registros__periodo__estado__iexact=Periodo.Estado.ABIERTO)
    ).filter(
        Q(compromisos__isnull=True)
        | Q(compromisos__agenda__periodo__estado__iexact=Periodo.Estado.ABIERTO)
    ).distinct()
    if request.GET.get('estado'):
        evidencias = evidencias.filter(estado=request.GET['estado'])
    if request.GET.get('desde'):
        evidencias = evidencias.filter(fecha__date__gte=request.GET['desde'])
    if request.GET.get('hasta'):
        evidencias = evidencias.filter(fecha__date__lte=request.GET['hasta'])
    if request.GET.get('q'):
        evidencias = evidencias.filter(Q(codigo__icontains=request.GET['q']) | Q(registros__descripcion__icontains=request.GET['q'])).distinct()

    evidencias, total_encontrados, pagination_query, sort, direction = paginate_queryset(
        request, evidencias, default_ordering='fecha',
        allowed_ordering={'fecha': 'fecha', 'estado': 'estado'},
    )
    periods = Periodo.objects.order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    period = periods.filter(pk=int(period_id)).first() if period_id.isdecimal() else periodo_vigente(
        periods.filter(estado=Periodo.Estado.ABIERTO),
    )
    delegation = active_delegation(request)
    users = get_user_model().objects.filter(
        is_active=True,
        usuariocargo__cargo_id__in=ids_cargos_funcionario(),
        usuariocargo__fecha_fin__isnull=True,
        usuariodelegacion__fecha_fin__isnull=True,
    )
    if delegation:
        users = users.filter(usuariodelegacion__delegacion=delegation)
    elif not request.user.is_superuser:
        users = users.none()
    users = list(users.distinct().order_by('last_name', 'first_name', 'email'))
    activity_metrics = actividad_reciente(users, period)

    revisiones = RevisionEvidencia.objects.filter(
        verificador=request.user,
    ).select_related('evidencia').prefetch_related(
        'evidencia__registros',
        'evidencia__compromisos',
        'evidencia__atenciones_sociales',
    )[:20]

    return render(request, 'SupervisorApp/index.html', {
        'sgr_role': 'Verificación',
        'evidencias': evidencias,
        'pending_count': total_encontrados,
        'total_encontrados': total_encontrados,
        'pagination_query': pagination_query,
        'sort': sort,
        'direction': direction,
        'review_form': RevisionEvidenciaForm(),
        'revisiones': revisiones,
        'periodos': periods,
        'periodo_seleccionado': period,
        'actividad_funcionarios': [
            {'usuario': user, **activity_metrics.get(user.pk, {})}
            for user in users
        ],
        'sidebar_modules': (
            {'label': 'Validar evidencias', 'url_name': 'supervisor:home'},
        ),
    })
