import secrets
from datetime import datetime
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from AdminApp.audit import registrar_historial
from config.decorators import cargo_required
from config.delegations import active_delegation
from CoordinadorApp.models import Desempeno, Periodo
from DelegadoApp.forms import AusenciaForm, CompromisoEstadoForm, CompromisoForm
from DelegadoApp.models import (
    Agenda, Ausencia, Compromiso, HistorialEstadoCompromiso,
    HistorialReasignacionCompromiso, SeguimientoAcceso,
)
from DelegadoApp.services import actualizar_compromiso, actualizar_estado_compromiso, detalle_actividades, marcar_compromisos_vencidos, resumen_delegacion


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
            'responsable', 'historial_estados', 'historial_reasignaciones__autor'
        )
        marcar_compromisos_vencidos(commitments, request.user)

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
                    if actualizar_compromiso(
                        compromiso=compromiso,
                        autor=request.user,
                        nuevo_estado=new_state,
                        observaciones=state_form.cleaned_data.get('observaciones', ''),
                        responsables=list(compromiso.responsable.all()),
                        action='Actualizar compromiso desde Delegado',
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
                        'fecha_compromiso': commitment.fecha_compromiso.isoformat(),
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
                    'fecha_compromiso': commitment.fecha_compromiso.isoformat(),
                    'estado': commitment.estado,
                    'observaciones': commitment.observaciones,
                }
            previous_state = commitment.estado if commitment else ''
            previous_responsables = (
                sorted(commitment.responsable.values_list('pk', flat=True))
                if commitment else []
            )
            commitment = form.save(commit=False)
            commitment.agenda = agenda
            with transaction.atomic():
                commitment.save()
                form.save_m2m()
                new_responsables = sorted(commitment.responsable.values_list('pk', flat=True))
                if previous_responsables != new_responsables:
                    HistorialReasignacionCompromiso.objects.create(
                        compromiso=commitment,
                        responsables_anteriores=previous_responsables,
                        responsables_nuevos=new_responsables,
                        autor=request.user,
                        motivo=form.cleaned_data['motivo_reasignacion'].strip(),
                    )
                new_snapshot = {
                    'descripcion': commitment.descripcion,
                    'fecha_compromiso': commitment.fecha_compromiso.isoformat(),
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
            {'label': 'Ausencias justificadas', 'url_name': 'delegado:ausencias'},
        ),
    })


@cargo_required('delegado', permission='manage_delegation_absences')
def ausencias(request):
    delegation = active_delegation(request)
    funcionarios = get_user_model().objects.filter(
        is_active=True,
        usuariodelegacion__delegacion=delegation,
        usuariodelegacion__fecha_fin__isnull=True,
    ).distinct().order_by('email') if delegation else get_user_model().objects.none()
    desempenos = Desempeno.objects.filter(
        usuario__in=funcionarios,
        periodo__estado=Periodo.Estado.ABIERTO,
    ).select_related('usuario', 'item', 'periodo').order_by(
        'usuario__email', 'periodo__nombre', 'item__nombre',
    )
    if request.method == 'POST':
        if request.POST.get('action') == 'eliminar':
            ausencia = get_object_or_404(
                Ausencia.objects.filter(usuario__in=funcionarios),
                pk=request.POST.get('ausencia_id'),
            )
            before = {'fecha_inicio': str(ausencia.fecha_inicio), 'fecha_fin': str(ausencia.fecha_fin), 'tipo': ausencia.tipo}
            ausencia.delete()
            registrar_historial(actor=request.user, action='Eliminar ausencia justificada', entity=f'Ausencia:{request.POST.get("ausencia_id")}', before=before, period=ausencia.periodo)
            messages.success(request, 'La ausencia fue eliminada.')
            return redirect('delegado:ausencias')
        form = AusenciaForm(request.POST, desempenos=desempenos)
        if form.is_valid():
            ausencia = form.save(commit=False)
            ausencia.usuario = ausencia.desempeno.usuario
            ausencia.item = ausencia.desempeno.item
            ausencia.periodo = ausencia.desempeno.periodo
            ausencia.fecha = timezone.make_aware(datetime.combine(ausencia.fecha_inicio, datetime.min.time()))
            ausencia.save()
            registrar_historial(actor=request.user, action='Crear ausencia justificada', entity=f'Ausencia:{ausencia.pk}', after={'usuario_id': ausencia.usuario_id, 'tipo': ausencia.tipo, 'fecha_inicio': str(ausencia.fecha_inicio), 'fecha_fin': str(ausencia.fecha_fin)}, period=ausencia.periodo)
            messages.success(request, 'La ausencia justificada quedó registrada.')
            return redirect('delegado:ausencias')
    else:
        form = AusenciaForm(desempenos=desempenos)
    registros = Ausencia.objects.filter(usuario__in=funcionarios).select_related('usuario', 'desempeno', 'item', 'periodo').order_by('-fecha_inicio', '-pk')
    return render(request, 'DelegadoApp/ausencias.html', {
        'sgr_role': 'Delegación',
        'form': form,
        'ausencias': registros,
        'sidebar_modules': (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
            {'label': 'Ausencias justificadas', 'url_name': 'delegado:ausencias'},
            {'label': 'Tubo de Cartas', 'url_name': 'funcionario:tubo_cartas'},
        ),
    })

def _resumen_excel_response(request, *, delegation, period, rows, **_metadata):
    """Construye el resumen de delegación como un XLSX formateado."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    headers = [
        'Funcionario', 'Correo', 'Cumplimiento (%)', 'Esperado (%)',
        'Semáforo', 'Último registro', 'Fecha último registro',
        'Días sin ingreso', 'Promedio diario',
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Resumen'
    sheet.sheet_view.showGridLines = False

    red = 'B91C1C'
    neutral = '374151'
    thin = Side(style='thin', color='D1D5DB')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill('solid', fgColor=red)
    neutral_fill = PatternFill('solid', fgColor='F3F4F6')
    zebra_fill = PatternFill('solid', fgColor='F9FAFB')
    semaforo_fills = {
        'verde': PatternFill('solid', fgColor='DCFCE7'),
        'ambar': PatternFill('solid', fgColor='FEF3C7'),
        'rojo': PatternFill('solid', fgColor='FEE2E2'),
    }

    total_columns = len(headers)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_columns)
    title = sheet.cell(1, 1, 'Resumen de desempeño de delegación')
    title.font = Font(name='Calibri', size=16, bold=True, color=neutral)
    title.fill = neutral_fill
    sheet.row_dimensions[1].height = 28

    generated_at = timezone.localtime().replace(tzinfo=None)
    metadata = (
        ('Delegación', str(delegation)),
        ('Trimestre', getattr(period, 'nombre', '') if period else 'Sin período'),
        ('Generado por', request.user.get_full_name() or request.user.email),
        ('Fecha', generated_at),
    )
    for row_number, (label, value) in enumerate(metadata, start=2):
        label_cell = sheet.cell(row_number, 1, label)
        label_cell.font = Font(bold=True, color=neutral)
        label_cell.fill = neutral_fill
        sheet.cell(row_number, 2, value)
        sheet.merge_cells(start_row=row_number, start_column=2, end_row=row_number, end_column=total_columns)
        for column in range(1, total_columns + 1):
            sheet.cell(row_number, column).border = border
    sheet['B5'].number_format = 'dd/mm/yyyy hh:mm:ss'

    header_row = 7
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, column, header)
        cell.fill = header_fill
        cell.font = Font(bold=True, color='FFFFFF')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    sheet.row_dimensions[header_row].height = 30

    for row_number, row in enumerate(rows, start=header_row + 1):
        values = [
            row['usuario'].get_full_name() or row['usuario'].email,
            row['usuario'].email,
            row['cumplimiento'], row['esperado'], row['semaforo'].title(),
            row.get('ultimo_registro') or 'Sin registros',
            row.get('fecha_ultimo_registro'), row.get('dias_sin_ingreso'),
            row.get('promedio_diario', 0),
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row_number, column, value)
            cell.border = border
            cell.alignment = Alignment(vertical='center', wrap_text=column in {1, 2, 6})
            if row_number % 2 == 0:
                cell.fill = zebra_fill
        sheet.cell(row_number, 3).number_format = '0.00"%"'
        sheet.cell(row_number, 4).number_format = '0.00"%"'
        sheet.cell(row_number, 7).number_format = 'dd/mm/yyyy'
        sheet.cell(row_number, 9).number_format = '0.00'
        sheet.cell(row_number, 5).fill = semaforo_fills.get(
            str(row['semaforo']).casefold(), zebra_fill,
        )
        sheet.row_dimensions[row_number].height = 24

    widths = (28, 34, 18, 16, 14, 42, 23, 18, 18)
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = 'A8'
    sheet.auto_filter.ref = f'A{header_row}:{get_column_letter(total_columns)}{sheet.max_row}'

    output = BytesIO()
    workbook.save(output)
    registrar_historial(
        actor=request.user,
        action='Exportar resumen de delegación XLSX',
        entity='ResumenDelegacion',
        after={'periodo': period.pk if period else None, 'filas': len(rows)},
        period=period,
    )
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="resumen_delegacion.xlsx"'
    return response


@cargo_required('delegado', permission='view_delegation_summary')
def resumen(request):

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
    if request.GET.get('export') == 'xlsx':
        if not delegation:
            messages.error(request, 'Tu cuenta no tiene delegación asignada.')
            return redirect('delegado:resumen')
        return _resumen_excel_response(
            request=request,
            delegation=delegation,
            period=selected_period,
            rows=filter_options['funcionarios'],
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
