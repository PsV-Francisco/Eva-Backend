import secrets
from datetime import datetime

from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from AdminApp.audit import registrar_historial
from config.decorators import cargo_required
from config.delegations import active_delegation
from CoordinadorApp.models import Periodo
from DelegadoApp.forms import CompromisoEstadoForm, CompromisoForm
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso, SeguimientoAcceso
from DelegadoApp.services import actualizar_estado_compromiso, detalle_actividades, resumen_delegacion


def _tracking_ip_key(ip_address):
    return f'seguimiento_publico:{ip_address}:attempts'


def _log_tracking_access(*, compromiso, token, request, success, reason):
    ip_address = request.META.get('REMOTE_ADDR') or None
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    SeguimientoAcceso.objects.create(
        compromiso=compromiso,
        token=(token or '')[:64],
        ip_address=ip_address,
        user_agent=user_agent,
        exito=success,
        motivo=reason,
    )


@require_GET
def seguimiento_publico(request, token):
    ip_address = request.META.get('REMOTE_ADDR') or 'unknown'
    rate_key = _tracking_ip_key(ip_address)
    attempts = cache.get(rate_key, 0)
    if attempts >= 10:
        _log_tracking_access(
            compromiso=None,
            token=token,
            request=request,
            success=False,
            reason='limitado',
        )
        return render(
            request,
            'DelegadoApp/seguimiento_publico.html',
            {
                'public_error': 'El seguimiento solicitado no está disponible en este momento.',
                'public_access_denied': True,
            },
            status=429,
        )

    cache.set(rate_key, attempts + 1, timeout=300)
    compromiso = Compromiso.objects.filter(seguimiento_token=token).select_related(
        'agenda', 'agenda__periodo', 'agenda__delegacion', 'solicitante', 'territorio'
    ).prefetch_related('historial_estados').first()

    if not compromiso or not compromiso.seguimiento_activo:
        _log_tracking_access(
            compromiso=compromiso,
            token=token,
            request=request,
            success=False,
            reason='desactivado' if compromiso and not compromiso.seguimiento_activo else 'invalido',
        )
        return render(
            request,
            'DelegadoApp/seguimiento_publico.html',
            {
                'public_error': 'El seguimiento solicitado no está disponible en este momento.',
                'public_access_denied': True,
            },
            status=404,
        )

    if compromiso.seguimiento_expira and timezone.now() > compromiso.seguimiento_expira:
        _log_tracking_access(
            compromiso=compromiso,
            token=token,
            request=request,
            success=False,
            reason='vencido',
        )
        return render(
            request,
            'DelegadoApp/seguimiento_publico.html',
            {
                'public_error': 'El seguimiento solicitado no está disponible en este momento.',
                'public_access_denied': True,
            },
            status=410,
        )

    compromiso.seguimiento_ultima_vista = timezone.now()
    compromiso.save(update_fields=['seguimiento_ultima_vista'])
    _log_tracking_access(
        compromiso=compromiso,
        token=token,
        request=request,
        success=True,
        reason='valido',
    )

    estados = [
        {'key': Compromiso.Estado.INGRESADO, 'label': 'Ingresado'},
        {'key': Compromiso.Estado.PENDIENTE, 'label': 'Pendiente'},
        {'key': Compromiso.Estado.EN_PROCESO, 'label': 'En proceso'},
        {'key': Compromiso.Estado.REALIZADO, 'label': 'Realizado'},
    ]
    
    # Manejo seguro por si el estado actual no se encuentra en la lista
    match_item = next((item for item in estados if item['key'] == compromiso.estado), None)
    current_index = estados.index(match_item) if match_item else 0

    timeline = []
    for index, estado in enumerate(estados):
        timeline.append({
            'label': estado['label'],
            'active': index <= current_index,
            'current': index == current_index,
            'done': index < current_index,
        })

    return render(request, 'DelegadoApp/seguimiento_publico.html', {
        'compromiso': compromiso,
        'timeline': timeline,
        'public_access_denied': False,
        'public_code': compromiso.codigo_publico,
        'historial': compromiso.historial_estados.select_related('autor').all(),
    })


@cargo_required('delegado', permission='manage_commitments')
def home(request):
    delegation = active_delegation(request)
    delegation_id = delegation.pk if delegation else None
    commitments = Compromiso.objects.none()
    if delegation_id:
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
        ).select_related(
            'agenda', 'agenda__periodo', 'solicitante', 'territorio'
        ).prefetch_related(
            'responsable', 'historial_estados'
        )

    if request.method == 'POST' and request.POST.get('action') == 'estado':
        if not delegation_id:
            messages.error(request, 'Tu cuenta no tiene una delegación asignada.')
        else:
            compromiso = get_object_or_404(commitments, pk=request.POST.get('compromiso_id'))
            if compromiso.agenda.periodo.estado != Periodo.Estado.ABIERTO:
                messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            else:
                state_form = CompromisoEstadoForm(request.POST)
                if state_form.is_valid():
                    new_state = state_form.cleaned_data['estado']
                    if actualizar_estado_compromiso(
                        compromiso=compromiso,
                        autor=request.user,
                        nuevo_estado=new_state,
                    ):
                        messages.success(request, 'El estado y su historial quedaron actualizados.')
                    else:
                        messages.info(request, 'El compromiso ya tenía ese estado.')
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

        if action == 'seguimiento_regenerar':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas actualizar.')
            else:
                commitment.seguimiento_token = secrets.token_urlsafe(32)
                commitment.seguimiento_activo = True
                commitment.seguimiento_expira = None
                commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo', 'seguimiento_expira'])
                messages.success(request, 'El enlace de seguimiento se regeneró correctamente. El enlace anterior dejó de funcionar.')
            return redirect('delegado:home')

        if action == 'seguimiento_toggle':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas actualizar.')
            else:
                commitment.seguimiento_activo = request.POST.get('seguimiento_activo') == '1'
                if not commitment.seguimiento_activo and not commitment.seguimiento_token:
                    commitment.seguimiento_token = secrets.token_urlsafe(32)
                commitment.save(update_fields=['seguimiento_activo', 'seguimiento_token'])
                messages.success(
                    request,
                    'El enlace de seguimiento se activó.' if commitment.seguimiento_activo else 'El enlace de seguimiento se desactivó.',
                )
            return redirect('delegado:home')

        if action == 'seguimiento_expiracion':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas actualizar.')
            else:
                fecha_input = request.POST.get('seguimiento_expira')
                if fecha_input:
                    # Convertir a datetime final del día en la zona horaria del sistema
                    dt = datetime.strptime(fecha_input, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                    commitment.seguimiento_expira = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                    if not commitment.seguimiento_token:
                        commitment.seguimiento_token = secrets.token_urlsafe(32)
                    commitment.seguimiento_activo = True
                    commitment.save(update_fields=['seguimiento_expira', 'seguimiento_activo', 'seguimiento_token'])
                    messages.success(request, 'Se configuró la fecha de vencimiento del enlace de seguimiento.')
                else:
                    commitment.seguimiento_expira = None
                    commitment.save(update_fields=['seguimiento_expira'])
                    messages.success(request, 'El enlace de seguimiento quedó sin fecha de vencimiento.')
            return redirect('delegado:home')

        if action == 'eliminar':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas eliminar.')
            elif bool(commitment.evidencia_id):
                messages.error(request, 'No se puede eliminar un compromiso con evidencias asociadas.')
            elif commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
                messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            else:
                try:
                    before = {
                        'descripcion': commitment.descripcion,
                        'fecha': commitment.fecha.isoformat(),
                        'estado': commitment.estado,
                        'observaciones': commitment.observaciones,
                    }
                    entity = f'Compromiso:{commitment.pk}'
                    period = commitment.agenda.periodo
                    with transaction.atomic():
                        commitment.delete()
                        registrar_historial(
                            actor=request.user,
                            action='Eliminar compromiso',
                            entity=entity,
                            before=before,
                            period=period,
                        )
                    messages.success(request, 'El compromiso se eliminó correctamente.')
                except ProtectedError:
                    messages.error(request, 'No se puede eliminar un compromiso que tiene información asociada.')
            return redirect('delegado:home')

        if commitment and bool(commitment.evidencia_id):
            messages.error(request, 'No se puede modificar un compromiso con evidencias asociadas.')
            return redirect('delegado:home')
        if commitment and commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
            messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            return redirect('delegado:home')

        if not delegation_id:
            messages.error(request, 'Asigna una delegación a tu cuenta antes de crear compromisos.')
            return redirect('delegado:home')

        form = CompromisoForm(
            request.POST, user=request.user, delegation=delegation,
            instance=commitment,
        )
        if form.is_valid():
            period = form.cleaned_data['periodo']
            agenda, _ = Agenda.objects.get_or_create(
                delegacion_id=delegation_id, periodo=period,
            )
            before = None
            if commitment:
                before = {
                    'descripcion': commitment.descripcion,
                    'fecha': commitment.fecha.isoformat(),
                    'estado': commitment.estado,
                    'observaciones': commitment.observaciones,
                }
            previous_state = commitment.estado if commitment else ''
            commitment = form.save(commit=False)
            commitment.agenda = agenda
            with transaction.atomic():
                commitment.save()
                form.save_m2m()
                new_snapshot = {
                    'descripcion': commitment.descripcion,
                    'fecha': commitment.fecha.isoformat(),
                    'estado': commitment.estado,
                    'observaciones': commitment.observaciones,
                }
                if previous_state != commitment.estado:
                    HistorialEstadoCompromiso.objects.create(
                        compromiso=commitment,
                        estado_anterior=previous_state,
                        estado_nuevo=commitment.estado,
                        autor=request.user,
                    )
                registrar_historial(
                    actor=request.user,
                    action='Editar compromiso' if before else 'Crear compromiso',
                    entity=f'Compromiso:{commitment.pk}',
                    before=before,
                    after=new_snapshot,
                    period=period,
                )
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
        form = CompromisoForm(
            instance=commitment, user=request.user, delegation=delegation,
        )

    return render(request, 'DelegadoApp/index.html', {
        'sgr_role': 'Delegación', 'form': form, 'commitments': commitments[:30],
        'commitment_count': commitments.count(), 'has_delegation': bool(delegation_id),
        'editing_commitment': commitment,
        'sidebar_modules': (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
            {'label': 'Tubo de Cartas', 'url_name': 'funcionario:tubo_cartas'},
        ),
    })

from AdminApp.csv_utils import csv_response
@cargo_required('delegado', permission='view_delegation_summary')
def resumen(request):
    from AdminApp.csv_utils import csv_response

    delegation = active_delegation(request)
    period_id = request.GET.get('periodo', '')
    funcionario_id = request.GET.get('funcionario', '')
    selected_period = (
        Periodo.objects.filter(pk=int(period_id)).first()
        if period_id.isdecimal()
        else Periodo.objects.filter(
            estado=Periodo.Estado.ABIERTO,
        ).order_by('-fecha_inicio').first()
    )
    periods = Periodo.objects.order_by('-fecha_inicio')
    summary = resumen_delegacion(
        delegation=delegation,
        period=selected_period,
        funcionario_id=int(funcionario_id) if funcionario_id.isdecimal() else None,
    )
    filter_options = (
        resumen_delegacion(delegation=delegation, period=selected_period)
        if funcionario_id else summary
    )
    detail_kind = request.GET.get('detalle', '')
    detail_users = summary.get('funcionarios', [])
    if detail_kind in {'verde', 'ambar', 'rojo'}:
        detail_users = [row for row in detail_users if row['semaforo'] == detail_kind]
    elif detail_kind == 'bajo':
        detail_users = summary.get('below_threshold', [])
    detail_records = detalle_actividades(
        user_ids=[row['usuario'].pk for row in detail_users],
        period=selected_period,
    ) if detail_kind else []
    if request.GET.get('export') == 'csv':
        if not delegation:
            messages.error(request, 'Tu cuenta no tiene delegación asignada.')
            return redirect('delegado:resumen')
        rows = [[
            'Funcionario',
            'Correo',
            'Cumplimiento (%)',
            'Esperado (%)',
            'Semáforo',
            'Último registro',
            'Fecha último registro',
            'Días sin ingreso',
            'Promedio diario',
        ]]
        rows.extend([
            row['usuario'].get_full_name() or row['usuario'].email,
            row['usuario'].email,
            row['cumplimiento'],
            row['esperado'],
            row['semaforo'],
            row['ultimo_registro'] or '',
            row['fecha_ultimo_registro'] or '',
            'Sin registros' if row.get('dias_sin_ingreso') is None else row['dias_sin_ingreso'],
            row.get('promedio_diario', ''),
        ] for row in summary['funcionarios'])
        return csv_response(
            request,
            filename='resumen_delegacion.csv',
            rows=rows,
            entity='ResumenDelegacion',
            action='Exportar resumen de delegación CSV',
            title='Resumen de desempeño por delegación',
            delegation=delegation,
            filters={'periodo': str(selected_period.pk) if selected_period else ''},
            row_count=len(summary['funcionarios']),
            period=selected_period,
        )

    return render(request, 'DelegadoApp/resumen.html', {
        'sgr_role': 'Delegación',
        'sidebar_modules': (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
            {'label': 'Tubo de Cartas', 'url_name': 'funcionario:tubo_cartas'},
        ),
        'periodos': periods,
        'periodo_seleccionado': selected_period,
        'ultima_actualizacion': timezone.localtime(),
        'funcionarios_filtro': filter_options.get('funcionarios', []),
        'selected_funcionario': funcionario_id,
        'detail_kind': detail_kind,
        'detail_records': detail_records,
        **summary,
    })
