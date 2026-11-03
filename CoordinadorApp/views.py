from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
import csv
import math
from io import StringIO
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from AdminApp.audit import registrar_historial
from AdminApp.maintainers import maintainer
from AdminApp.models import Cargo, Delegacion, ParametroSistema
from config.decorators import cargo_required
from CoordinadorApp.forms import PeriodoForm
from CoordinadorApp.models import Desempeno, Periodo, SolicitudAutorizacionPeriodo
from CoordinadorApp.authorization_forms import AuthorizationRequestForm
from CoordinadorApp.services import _authorization_snapshot
from CoordinadorApp.services import (
    clasificar_umbral,
    resumen_cumplimiento,
    tendencias_cumplimiento,
    umbral_delegacion,
    ZERO,
)
from DelegadoApp.models import Agenda
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


def _period_snapshot(periodo):
    return {
        'nombre': periodo.nombre,
        'fecha_inicio': periodo.fecha_inicio.isoformat(),
        'fecha_fin': periodo.fecha_fin.isoformat(),
        'estado': periodo.estado,
    }


def _has_associated_records(periodo):
    return (
        periodo.desempenos.exists()
        or periodo.registros.exists()
        or periodo.agendas.exists()
    )


def _periods_view(request):
    cargo_name = request.user.cargo.nombre.strip().casefold()
    is_coordinator = cargo_name == 'coordinador'
    can_reopen = cargo_name in {'coordinador', 'admin', 'administrador'}

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        periodo_id = request.POST.get('periodo_id')
        if action in {'cerrar', 'reabrir', 'eliminar'}:
            periodo = get_object_or_404(Periodo, pk=periodo_id)
            before = _period_snapshot(periodo)

            if action == 'reabrir':
                if not can_reopen:
                    messages.error(request, 'No tienes autorización para reabrir períodos.')
                elif periodo.estado == Periodo.Estado.ABIERTO:
                    messages.info(request, 'El período ya está abierto.')
                else:
                    with transaction.atomic():
                        periodo.estado = Periodo.Estado.ABIERTO
                        periodo.save(update_fields=['estado'])
                        registrar_historial(
                            actor=request.user,
                            action='Reabrir período',
                            entity=f'Periodo:{periodo.pk}',
                            before=before,
                            after=_period_snapshot(periodo),
                            period=periodo,
                        )
                    messages.success(request, 'El período se reabrió correctamente.')
            elif action == 'cerrar':
                if not is_coordinator:
                    messages.error(request, 'Solo Coordinación puede cerrar períodos.')
                elif periodo.estado == Periodo.Estado.CERRADO:
                    messages.info(request, 'El período ya está cerrado.')
                else:
                    with transaction.atomic():
                        periodo.estado = Periodo.Estado.CERRADO
                        periodo.save(update_fields=['estado'])
                        registrar_historial(
                            actor=request.user,
                            action='Cerrar período',
                            entity=f'Periodo:{periodo.pk}',
                            before=before,
                            after=_period_snapshot(periodo),
                            period=periodo,
                        )
                    messages.success(request, 'El período se cerró correctamente.')
            elif periodo.estado == Periodo.Estado.CERRADO:
                messages.error(request, 'Un período cerrado no se puede eliminar; primero debe reabrirse.')
            elif _has_associated_records(periodo):
                messages.error(request, 'Este período tiene información asociada. Ciérralo en lugar de eliminarlo.')
            elif not is_coordinator:
                messages.error(request, 'Solo Coordinación puede eliminar períodos.')
            else:
                entity = f'Periodo:{periodo.pk}'
                with transaction.atomic():
                    registrar_historial(
                        actor=request.user,
                        action='Eliminar período',
                        entity=entity,
                        before=before,
                    )
                    periodo.delete()
                messages.success(request, 'El período se eliminó correctamente.')
            return redirect('coordinador:periodos')

        instance = get_object_or_404(Periodo, pk=periodo_id) if periodo_id else None
        if not is_coordinator:
            messages.error(request, 'Solo Coordinación puede crear o editar períodos.')
            return redirect('coordinador:periodos')
        if instance and instance.estado == Periodo.Estado.CERRADO:
            messages.error(request, 'Un período cerrado es de solo lectura. Reábrelo para editarlo.')
            return redirect('coordinador:periodos')

        before = _period_snapshot(instance) if instance else None
        form = PeriodoForm(request.POST, instance=instance)
        if form.is_valid():
            with transaction.atomic():
                periodo = form.save()
                registrar_historial(
                    actor=request.user,
                    action='Editar período' if before else 'Crear período',
                    entity=f'Periodo:{periodo.pk}',
                    before=before,
                    after=_period_snapshot(periodo),
                    period=periodo,
                )
            messages.success(
                request,
                'El período se actualizó correctamente.' if instance
                else 'El período quedó configurado.',
            )
            return redirect('coordinador:periodos')
        messages.error(request, 'No se pudo guardar el período. Revisa las fechas y los campos.')
    else:
        edit_id = request.GET.get('editar')
        instance = get_object_or_404(Periodo, pk=edit_id) if edit_id else None
        if instance and instance.estado == Periodo.Estado.CERRADO:
            messages.error(request, 'Un período cerrado es de solo lectura. Reábrelo para editarlo.')
            return redirect('coordinador:periodos')
        if not is_coordinator:
            instance = None
        form = PeriodoForm(instance=instance)

    periodos = Periodo.objects.annotate(
        tiene_datos=(
            Exists(Desempeno.objects.filter(periodo_id=OuterRef('pk')))
            | Exists(Registro.objects.filter(periodo_id=OuterRef('pk')))
            | Exists(Agenda.objects.filter(periodo_id=OuterRef('pk')))
        ),
    )
    return render(request, 'CoordinadorApp/index.html', {
        'sgr_role': 'Coordinación', 'form': form, 'periodos': periodos,
        'editing_period': instance if is_coordinator else None,
        'can_manage_periods': is_coordinator,
        'can_reopen_periods': can_reopen,
        'sidebar_modules': _coordinator_management_modules(),
        'periodo_count': periodos.count(), 'periodos_abiertos': periodos.filter(estado=Periodo.Estado.ABIERTO).count(),
        'desempeno_count': Desempeno.objects.count(),
    })


@cargo_required(
    'coordinador', 'admin', 'administrador', permission='manage_coordinator_periods',
)
def periodos(request):
    return _periods_view(request)


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='manage_periods',
)
def home(request):
    if request.method == 'POST':
        # Compatibilidad con formularios antiguos sin perder el cuerpo POST.
        return _periods_view(request)

    edit_id = request.GET.get('editar')
    if edit_id:
        return redirect(f"{reverse('coordinador:periodos')}?editar={edit_id}")

    assigned_periods = Periodo.objects.filter(
        desempenos__usuario=request.user,
    ).distinct().order_by('-fecha_inicio')
    period_id = request.GET.get('periodo')
    period = (
        assigned_periods.filter(pk=int(period_id)).first()
        if period_id and period_id.isdecimal()
        else None
    ) or assigned_periods.first()
    performances = (
        Desempeno.objects.filter(
            usuario=request.user, periodo=period,
        ).select_related('item', 'periodo')
        if period else Desempeno.objects.none()
    )
    summary = resumen_cumplimiento(performances)
    has_items = bool(summary['items'])
    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': (
            {'label': 'Tablero Personal', 'url_name': 'coordinador:home'},
            {'label': 'Gestión de períodos', 'url_name': 'coordinador:periodos'},
        ),
        'periodos': assigned_periods,
        'periodo_seleccionado': period,
        'summary': summary,
        'item_count': len(summary['items']),
        'umbral_delegacion': umbral_delegacion(),
        'clasificacion_umbral': clasificar_umbral(
            summary['avance_real'], tiene_items=has_items,
        ),
    })


def _coordinator_management_modules():
    return (
        {'label': 'Tablero Personal', 'url_name': 'coordinador:home'},
        {'label': 'Gestión de períodos', 'url_name': 'coordinador:periodos'},
        {'label': 'Gestión de metas', 'url_name': 'coordinador:metas'},
        {'label': 'Funciones por cargo', 'url_name': 'coordinador:cargos_funciones'},
        {'label': 'Ponderaciones', 'url_name': 'coordinador:ponderaciones'},
        {'label': 'Informes de gestión', 'url_name': 'coordinador:informes'},
        {'label': 'Tendencias históricas', 'url_name': 'coordinador:tendencias'},
        {'label': 'Solicitar autorización', 'url_name': 'coordinador:solicitudes_autorizacion'},
    )


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='request_closed_period_authorization',
)
def solicitudes_autorizacion(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'cancelar':
            solicitud = get_object_or_404(
                SolicitudAutorizacionPeriodo,
                pk=request.POST.get('solicitud_id'),
                solicitante=request.user,
                estado=SolicitudAutorizacionPeriodo.Estado.PENDIENTE,
            )
            before = _authorization_snapshot(solicitud)
            solicitud.estado = SolicitudAutorizacionPeriodo.Estado.CANCELADA
            solicitud.decidida_en = timezone.now()
            solicitud.save(update_fields=['estado', 'decidida_en'])
            registrar_historial(
                actor=request.user,
                action='Cancelar solicitud de autorización',
                entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}',
                before=before,
                after=_authorization_snapshot(solicitud),
                period=solicitud.periodo,
            )
            messages.success(request, 'La solicitud fue cancelada.')
            return redirect('coordinador:solicitudes_autorizacion')
        form = AuthorizationRequestForm(request.POST)
        if form.is_valid():
            solicitud = form.save(commit=False)
            solicitud.solicitante = request.user
            solicitud.alcances = ['metas']
            solicitud.save()
            form.save_m2m()
            registrar_historial(
                actor=request.user,
                action='Solicitar autorización de período',
                entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}',
                after=_authorization_snapshot(solicitud),
                period=solicitud.periodo,
            )
            messages.success(request, 'La solicitud quedó pendiente de revisión.')
            return redirect('coordinador:solicitudes_autorizacion')
    else:
        form = AuthorizationRequestForm()
    solicitudes = SolicitudAutorizacionPeriodo.objects.filter(
        solicitante=request.user,
    ).select_related('periodo').prefetch_related('funcionarios')
    return render(request, 'CoordinadorApp/solicitudes_autorizacion.html', {
        'sgr_role': 'Coordinación',
        'form': form,
        'solicitudes': solicitudes,
        'sidebar_modules': _coordinator_management_modules(),
    })


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='manage_coordinator_goals',
)
def metas(request):
    return maintainer(
        request,
        'metas',
        route_name='coordinador:metas',
        sgr_role='Coordinación',
        sidebar_modules=_coordinator_management_modules(),
        protect_closed_periods=True,
        global_scope=True,
        coordinator_meta_delete=True,
        warn_weight_total=True,
        closed_period_authorization=True,
    )


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='manage_coordinator_position_functions',
)
def cargos_funciones(request):
    return maintainer(
        request,
        'cargos-funciones',
        route_name='coordinador:cargos_funciones',
        sgr_role='Coordinación',
        sidebar_modules=_coordinator_management_modules(),
        global_scope=True,
    )


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='view_coordinator_weights',
)
def ponderaciones(request):
    period_id = request.GET.get('periodo', '')
    cargo_id = request.GET.get('cargo', '')
    user_id = request.GET.get('funcionario', '')
    queryset = Desempeno.objects.select_related(
        'item', 'periodo', 'usuario',
    ).order_by('periodo__fecha_inicio', 'usuario__email', 'item__nombre')
    if period_id.isdecimal():
        queryset = queryset.filter(periodo_id=period_id)
    if cargo_id.isdecimal():
        queryset = queryset.filter(
            usuario__usuariocargo__cargo_id=cargo_id,
            usuario__usuariocargo__fecha_fin__isnull=True,
        ).distinct()
    if user_id.isdecimal():
        queryset = queryset.filter(usuario_id=user_id)

    grouped = {}
    for record in queryset:
        key = (record.periodo_id, record.usuario_id)
        grouped.setdefault(key, {
            'periodo': record.periodo,
            'usuario': record.usuario,
            'cargo': record.usuario.cargo,
            'rows': [],
            'total': Decimal('0'),
        })
        grouped[key]['rows'].append(record)
        grouped[key]['total'] += record.item.ponderacion or Decimal('0')
    summaries = []
    for summary in grouped.values():
        total = summary['total']
        summary['total'] = total
        summary['status'] = (
            'Cumple 100 %' if total == 100
            else 'Incompleta' if total < 100
            else 'Excede 100 %'
        )
        summaries.append(summary)

    return render(request, 'CoordinadorApp/ponderaciones.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': _coordinator_management_modules(),
        'summaries': summaries,
        'periodos': Periodo.objects.order_by('-fecha_inicio'),
        'cargos': Cargo.objects.filter(estado=Cargo.Estado.ACTIVO).order_by('nombre'),
        'funcionarios': get_user_model().objects.filter(
            is_active=True,
        ).order_by('last_name', 'first_name', 'email'),
        'selected_period': period_id,
        'selected_cargo': cargo_id,
        'selected_user': user_id,
    })


def _csv_safe(value):
    value = '' if value is None else str(value)
    return "'" + value if value[:1] in {'=', '+', '-', '@'} else value


def _report_filters(request):
    periods = Periodo.objects.order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    if period_id.isdecimal():
        period = periods.filter(pk=period_id).first()
    else:
        period = periods.filter(estado=Periodo.Estado.ABIERTO).first() or periods.first()
    delegation_id = request.GET.get('delegacion', '')
    cargo_id = request.GET.get('cargo', '')
    user_id = request.GET.get('funcionario', '')
    return periods, period, period_id, delegation_id, cargo_id, user_id


def _consolidated_report_rows(request):
    periods, period, period_id, delegation_id, cargo_id, user_id = _report_filters(request)
    cap = ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO)
    threshold = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION)
    users = get_user_model().objects.filter(
        is_active=True,
    ).order_by('last_name', 'first_name', 'email')
    if delegation_id.isdecimal():
        users = users.filter(
            usuariodelegacion__delegacion_id=delegation_id,
            usuariodelegacion__fecha_fin__isnull=True,
        ).distinct()
    if cargo_id.isdecimal():
        users = users.filter(
            usuariocargo__cargo_id=cargo_id,
            usuariocargo__fecha_fin__isnull=True,
        ).distinct()
    if user_id.isdecimal():
        users = users.filter(pk=user_id)
    users = list(users)
    user_ids = {user.pk for user in users}
    performances = Desempeno.objects.none()
    if period and user_ids:
        performances = Desempeno.objects.filter(
            periodo=period, usuario_id__in=user_ids,
        ).select_related('item', 'periodo', 'usuario')
    performances = list(performances)
    counts = {
        (row['autor_id'], row['item_id'], row['periodo_id']): row['cantidad']
        for row in Registro.objects.filter(
            autor_id__in=user_ids,
            periodo_id=period.pk if period else None,
            estado=Registro.Estado.VALIDADA,
            evidencias_registros__estado=Evidencia.Estado.APROBADA,
        ).values('autor_id', 'item_id', 'periodo_id').annotate(
            cantidad=Count('pk', distinct=True),
        )
    } if period and user_ids else {}
    performances_by_user = defaultdict(list)
    for performance in performances:
        performances_by_user[performance.usuario_id].append(performance)
    rows = []
    summaries = defaultdict(lambda: {
        'delegacion': '', 'cargo': '', 'total_avance_real': ZERO,
        'con_items': 0, 'sobre': 0, 'bajo': 0, 'sin_items': 0,
    })
    for user in users:
        summary = resumen_cumplimiento(
            performances_by_user[user.pk], counts=counts, cap=cap,
        )
        classification = clasificar_umbral(
            summary['avance_real'], tiene_items=bool(summary['items']), umbral=threshold,
        )
        delegation = user.delegacion.nombre if user.delegacion_id else 'Sin delegación'
        cargo = user.cargo.nombre if user.cargo_id else 'Sin cargo'
        group = summaries[(delegation, cargo)]
        group['delegacion'] = delegation
        group['cargo'] = cargo
        if summary['items']:
            group['total_avance_real'] += summary['avance_real']
            group['con_items'] += 1
            group[classification] += 1
        else:
            group['sin_items'] += 1
        rows.append({
            'usuario': user,
            'delegacion': delegation,
            'cargo': cargo,
            'summary': summary,
            'clasificacion': classification,
        })
    for group in summaries.values():
        group['promedio_avance_real'] = (
            group['total_avance_real'] / group['con_items']
            if group['con_items'] else ZERO
        ).quantize(Decimal('0.01'))
    return periods, period, period_id or (str(period.pk) if period else ''), delegation_id, cargo_id, user_id, rows, list(summaries.values())


@cargo_required(
    'coordinador', 'admin', 'administrador', permission='view_coordinator_reports',
)
def informes(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    data = _consolidated_report_rows(request)
    periods, period, period_id, delegation_id, cargo_id, user_id, rows, summaries = data
    if request.GET.get('export') == 'csv':
        output = StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Informe consolidado'])
        writer.writerow(['Período', period.nombre if period else ''])
        writer.writerow([])
        writer.writerow(['Detalle', 'Delegación', 'Cargo', 'Funcionario', 'Avance real', 'Avance esperado', 'Clasificación', 'Ítems'])
        for row in rows:
            summary = row['summary']
            writer.writerow([
                _csv_safe(''), _csv_safe(row['delegacion']), _csv_safe(row['cargo']),
                _csv_safe(row['usuario'].get_full_name() or row['usuario'].email),
                summary['avance_real'], summary['avance_esperado'],
                _csv_safe(row['clasificacion'] or 'Sin ítems'), len(summary['items']),
            ])
        writer.writerow([])
        writer.writerow(['Resumen consolidado'])
        writer.writerow(['Delegación', 'Cargo', 'Promedio avance real', 'Sobre umbral', 'Bajo umbral', 'Sin ítems'])
        for summary in summaries:
            writer.writerow([_csv_safe(summary['delegacion']), _csv_safe(summary['cargo']), summary['promedio_avance_real'], summary['sobre'], summary['bajo'], summary['sin_items']])
        registrar_historial(
            actor=request.user,
            action='Exportar informe consolidado CSV',
            entity='InformeConsolidado',
            after={
                'filtros': {'periodo': period_id, 'delegacion': delegation_id, 'cargo': cargo_id, 'funcionario': user_id},
                'filas': len(rows),
            },
            period=period,
        )
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="informe_consolidado.csv"'
        return response
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'CoordinadorApp/informes.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': _coordinator_management_modules(),
        'page_obj': page,
        'summaries': summaries,
        'periodos': periods,
        'delegaciones': Delegacion.objects.order_by('nombre'),
        'cargos': Cargo.objects.filter(estado=Cargo.Estado.ACTIVO).order_by('nombre'),
        'funcionarios': get_user_model().objects.filter(is_active=True).order_by('last_name', 'first_name', 'email'),
        'selected_period': period_id,
        'selected_delegation': delegation_id,
        'selected_cargo': cargo_id,
        'selected_user': user_id,
        'periodo_seleccionado': period,
    })


def _trend_range(raw_value):
    if raw_value in (None, ''):
        return 6, ''
    if not raw_value.isdecimal():
        return 6, 'El rango indicado no es válido; se muestran los últimos 6 períodos.'
    normalized = raw_value.lstrip('0')
    if not normalized:
        return 6, 'El rango indicado no es válido; se muestran los últimos 6 períodos.'
    if len(normalized) > 2:
        return 12, 'El rango máximo es 12 períodos; se limitaron los resultados.'
    value = int(normalized)
    if value <= 0:
        return 6, 'El rango indicado no es válido; se muestran los últimos 6 períodos.'
    if value > 12:
        return 12, 'El rango máximo es 12 períodos; se limitaron los resultados.'
    return value, ''


def _trend_filter_id(raw_value, label):
    if raw_value in (None, ''):
        return None, ''
    if not raw_value.isdecimal():
        return None, f'El identificador de {label} no es válido; no hay resultados para ese filtro.'
    normalized = raw_value.lstrip('0')
    if (
        not normalized
        or len(normalized) > 19
        or (len(normalized) == 19 and normalized > '9223372036854775807')
    ):
        return None, f'El identificador de {label} no es válido; no hay resultados para ese filtro.'
    return int(normalized), ''


def _trend_chart(series, threshold):
    points = [row for row in series if row['funcionarios_considerados']]
    if len(points) < 2:
        return [], [], 100, 0

    max_value = max(
        max(row['promedio_avance_real'], row['porcentaje_sobre_umbral'])
        for row in points
    )
    chart_max = max(100, math.ceil(float(max_value) / 25) * 25)
    left, right, top, bottom = 82, 678, 40, 260
    plot_height = bottom - top
    chart_points = []
    for index, row in enumerate(points):
        x = round(left + (right - left) * index / (len(points) - 1))
        chart_points.append({
            **row,
            'x': x,
            'promedio_y': round(bottom - float(row['promedio_avance_real']) * plot_height / chart_max),
            'sobre_y': round(bottom - float(row['porcentaje_sobre_umbral']) * plot_height / chart_max),
        })
    ticks = [
        {'value': value, 'y': round(bottom - value * plot_height / chart_max)}
        for value in range(0, chart_max + 1, 25)
    ]
    threshold_y = round(bottom - float(threshold) * plot_height / chart_max)
    return chart_points, ticks, chart_max, threshold_y


@cargo_required(
    'coordinador', 'admin', 'administrador',
    permission='view_coordinator_trends',
)
def tendencias(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    period_limit, range_message = _trend_range(request.GET.get('periodos', ''))
    selected_periods = list(
        Periodo.objects.order_by('-fecha_inicio', '-pk')[:period_limit],
    )
    selected_periods.reverse()

    raw_filters = {
        'delegacion': request.GET.get('delegacion', ''),
        'cargo': request.GET.get('cargo', ''),
        'funcionario': request.GET.get('funcionario', ''),
    }
    parsed_filters = {}
    filter_message = ''
    for key, label in (
        ('delegacion', 'delegación'),
        ('cargo', 'cargo'),
        ('funcionario', 'funcionario'),
    ):
        parsed_filters[key], error = _trend_filter_id(raw_filters[key], label)
        if error and not filter_message:
            filter_message = error

    User = get_user_model()
    filter_models = {
        'delegacion': Delegacion,
        'cargo': Cargo,
        'funcionario': User,
    }
    filter_labels = {
        'delegacion': 'delegación',
        'cargo': 'cargo',
        'funcionario': 'funcionario',
    }
    for key, value in parsed_filters.items():
        if value is not None and not filter_models[key].objects.filter(pk=value).exists():
            filter_message = (
                f'No existe la opción seleccionada para el filtro de '
                f'{filter_labels[key]}; no hay resultados.'
            )
            break

    users = User.objects.filter(
        is_active=True,
    ).order_by('last_name', 'first_name', 'email')
    if parsed_filters['delegacion'] is not None:
        users = users.filter(
            usuariodelegacion__delegacion_id=parsed_filters['delegacion'],
            usuariodelegacion__fecha_fin__isnull=True,
        ).distinct()
    if parsed_filters['cargo'] is not None:
        users = users.filter(
            usuariocargo__cargo_id=parsed_filters['cargo'],
            usuariocargo__fecha_fin__isnull=True,
        ).distinct()
    if parsed_filters['funcionario'] is not None:
        users = users.filter(pk=parsed_filters['funcionario'])
    users = list(users) if not filter_message else []

    cap = ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO)
    threshold = umbral_delegacion()
    series = tendencias_cumplimiento(
        users,
        selected_periods,
        cap=cap,
        umbral=threshold,
    )
    chart_points, chart_ticks, chart_max, threshold_y = _trend_chart(
        series,
        threshold,
    )

    if filter_message:
        empty_message = filter_message
    elif not users:
        empty_message = 'No hay funcionarios activos que coincidan con los filtros seleccionados.'
    elif not selected_periods:
        empty_message = 'No hay períodos configurados para mostrar.'
    else:
        empty_message = ''

    if request.GET.get('export') == 'csv':
        output = StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([
            'Período',
            'Funcionarios considerados',
            'Promedio de avance real (%)',
            'Funcionarios sobre el umbral (%)',
            'Funcionarios sin ítems',
        ])
        for row in series:
            writer.writerow([
                _csv_safe(row['periodo'].nombre),
                row['funcionarios_considerados'],
                row['promedio_avance_real'],
                row['porcentaje_sobre_umbral'],
                row['funcionarios_sin_items'],
            ])
        registrar_historial(
            actor=request.user,
            action='Exportar tendencias históricas CSV',
            entity='TendenciasHistoricas',
            after={
                'filtros': {
                    **raw_filters,
                    'periodos': period_limit,
                },
                'filas': len(series),
            },
            period=selected_periods[-1] if selected_periods else None,
        )
        response = HttpResponse(
            '\ufeff' + output.getvalue(),
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="tendencias_historicas.csv"'
        return response

    return render(request, 'CoordinadorApp/tendencias.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': _coordinator_management_modules(),
        'series': series,
        'period_limit': period_limit,
        'range_message': range_message,
        'filter_message': filter_message,
        'empty_message': empty_message,
        'periodos': selected_periods,
        'delegaciones': Delegacion.objects.order_by('nombre'),
        'cargos': Cargo.objects.filter(estado=Cargo.Estado.ACTIVO).order_by('nombre'),
        'funcionarios': User.objects.filter(
            is_active=True,
        ).order_by('last_name', 'first_name', 'email'),
        'selected_delegation': raw_filters['delegacion'],
        'selected_cargo': raw_filters['cargo'],
        'selected_user': raw_filters['funcionario'],
        'chart_points': chart_points,
        'chart_ticks': chart_ticks,
        'chart_max': chart_max,
        'threshold': threshold,
        'threshold_y': threshold_y,
    })
