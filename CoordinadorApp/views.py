#Importaciones de Django
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from collections import defaultdict
from decimal import Decimal
import math
#Importaciones de AdminApp
from AdminApp.audit import registrar_historial
from AdminApp.csv_utils import csv_response
from AdminApp.maintainers import maintainer
from AdminApp.models import Cargo, Delegacion, ParametroSistema
from config.decorators import cargo_required
from config.permissions import cargo_key_for_access
from AdminApp.csv_utils import excel_rows_response, pdf_rows_response
#Importaciones de CoordinadorApp
from CoordinadorApp.forms import PeriodoForm
from CoordinadorApp.models import Desempeno, Periodo, SolicitudAutorizacionPeriodo
from CoordinadorApp.reporting import consolidated_report_csv_rows
from CoordinadorApp.authorization_forms import AuthorizationRequestForm
from CoordinadorApp.services import _authorization_snapshot, periodo_vigente
from CoordinadorApp.services import (clasificar_umbral,consolidar_cumplimientos,resumen_cumplimiento,tendencias_cumplimiento,umbral_delegacion,parametros_periodo,ZERO)
#Importaciones de Modelos Necesarios
from DelegadoApp.models import Agenda
from FuncionarioApp.models import Registro, Vecino
from SupervisorApp.models import Evidencia



def _period_snapshot(periodo):
    """
    Serializa los atributos clave de un objeto Periodo
    (nombre, fechas en formato ISO y estado) en un diccionario para registrar auditorías de cambios.
    """
    return {'nombre': periodo.nombre,'fecha_inicio': periodo.fecha_inicio.isoformat(),'fecha_fin': periodo.fecha_fin.isoformat(), 'estado': periodo.estado, 'semaforo_rojo': str(periodo.semaforo_rojo) if periodo.semaforo_rojo is not None else None, 'semaforo_ambar': str(periodo.semaforo_ambar) if periodo.semaforo_ambar is not None else None, 'umbral_delegacion': str(periodo.umbral_delegacion) if periodo.umbral_delegacion is not None else None, 'tope_cumplimiento': str(periodo.tope_cumplimiento) if periodo.tope_cumplimiento is not None else None}


def _has_associated_records(periodo):
    """
    Verifica si un período tiene registros asociados en desempeño,
    actividades o agendas para impedir su eliminación directa y mantener la integridad referencial.
    """
    return (periodo.desempenos.exists() or periodo.registros.exists() or periodo.agendas.exists())


def _periods_view(request):
    """
    Gestiona el ciclo de vida CRUD y los cambios de estado (abrir, cerrar, eliminar) de los períodos,
    validando permisos por cargo y registrando auditoría en el historial.
    """
    cargo = request.user.cargo
    cargo_name = cargo.nombre.strip().casefold() if cargo else ''
    is_coordinator = cargo_name == 'coordinador'
    # HU-28: solo Administración puede reabrir un período cerrado (queda en la bitácora).
    can_reopen = request.user.is_superuser or cargo_key_for_access(cargo_name) == 'admin'

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
                        rules = parametros_periodo(periodo)
                        periodo.estado = Periodo.Estado.CERRADO
                        periodo.semaforo_rojo = rules['rojo']
                        periodo.semaforo_ambar = rules['ambar']
                        periodo.umbral_delegacion = rules['delegacion']
                        periodo.tope_cumplimiento = rules['tope']
                        periodo.save(update_fields=['estado', 'semaforo_rojo', 'semaforo_ambar', 'umbral_delegacion', 'tope_cumplimiento'])
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


@cargo_required('coordinador', 'admin', 'administrador', permission='manage_coordinator_periods')
def periodos(request):
    """
    Vista principal que expone la gestión completa de períodos
    al delegar la ejecución en la lógica interna de administración de períodos.
    """
    return _periods_view(request)


@cargo_required('coordinador', 'admin', 'administrador',permission='manage_periods')
def home(request):
    """
    Renderiza el panel general de Coordinación con métricas clave de períodos,
    metas, funcionarios, registros y evidencias pendientes, manteniendo compatibilidad con envíos POST legados.
    """
    if request.method == 'POST':
        # Compatibilidad con formularios antiguos sin perder el cuerpo POST.
        return _periods_view(request)

    edit_id = request.GET.get('editar')
    if edit_id:
        return redirect(f"{reverse('coordinador:periodos')}?editar={edit_id}")

    periodos = Periodo.objects.order_by('-fecha_inicio', '-pk')
    period_id = request.GET.get('periodo', '')
    period = (
        periodos.filter(pk=period_id).first()
        if period_id.isdecimal()
        else None
    )
    if period is None:
        period = (
            periodo_vigente(periodos.filter(estado=Periodo.Estado.ABIERTO))
            or periodo_vigente(periodos)
        )

    desempenos = (
        Desempeno.objects.filter(periodo=period)
        if period else Desempeno.objects.none()
    )
    registros = (
        Registro.objects.filter(periodo=period)
        if period else Registro.objects.none()
    )
    evidencias_pendientes = (
        Evidencia.objects.filter(
            registros__periodo=period,
            estado=Evidencia.Estado.PENDIENTE,
        ).distinct()
        if period else Evidencia.objects.none()
    )
    return render(request, 'CoordinadorApp/dashboard.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': _coordinator_management_modules(),
        'periodos': periodos,
        'periodo_seleccionado': period,
        'open_period_count': periodos.filter(
            estado=Periodo.Estado.ABIERTO,
        ).count(),
        'closed_period_count': periodos.filter(
            estado=Periodo.Estado.CERRADO,
        ).count(),
        'goal_count': desempenos.count(),
        'employee_count': desempenos.values('usuario_id').distinct().count(),
        'activity_count': registros.count(),
        'validated_activity_count': registros.filter(
            estado=Registro.Estado.VALIDADA,
        ).count(),
        'pending_activity_count': registros.filter(
            estado=Registro.Estado.PENDIENTE,
        ).count(),
        'pending_evidence_count': evidencias_pendientes.count(),
        'ultima_actualizacion': timezone.localtime(),
    })


def _coordinator_management_modules():
    """
    Retorna la estructura de navegación lateral con las rutas y etiquetas de los módulos disponibles para el rol de Coordinación.
    """
    return (
        {'label': 'Panel de Coordinación', 'url_name': 'coordinador:home'},
        {'label': 'Tablero Personal', 'url_name': 'coordinador:personal'},
        {'label': 'Gestión de períodos', 'url_name': 'coordinador:periodos'},
        {'label': 'Gestión de metas', 'url_name': 'coordinador:metas'},
        {'label': 'Funciones por cargo', 'url_name': 'coordinador:cargos_funciones'},
        {'label': 'Ponderaciones', 'url_name': 'coordinador:ponderaciones'},
        {'label': 'Informes de gestión', 'url_name': 'coordinador:informes'},
        {'label': 'Tendencias históricas', 'url_name': 'coordinador:tendencias'},
        {'label': 'Solicitar autorización', 'url_name': 'coordinador:solicitudes_autorizacion'},
    )


@cargo_required('coordinador', 'admin', 'administrador',permission='view_coordinator_personal')
def personal(request):
    """
    Presenta el tablero de cumplimiento individual del usuario autenticado para el período seleccionado, evaluando su avance real frente al umbral de delegación.
    """
    edit_id = request.GET.get('editar')
    if edit_id:
        return redirect(f"{reverse('coordinador:periodos')}?editar={edit_id}")

    periodos = Periodo.objects.order_by('-fecha_inicio', '-pk')
    period_id = request.GET.get('periodo', '')
    period = (periodos.filter(pk=period_id).first() if period_id.isdecimal() else None)
    if period is None:
        period = (
            periodo_vigente(periodos.filter(estado=Periodo.Estado.ABIERTO))
            or periodo_vigente(periodos)
        )
    performances = (Desempeno.objects.filter(usuario=request.user, periodo=period,).select_related('item', 'periodo')
        if period else Desempeno.objects.none())
    
    summary = resumen_cumplimiento(performances)
    has_items = bool(summary['items'])
    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Coordinación',
        'sidebar_modules': _coordinator_management_modules(),
        'periodos': periodos,
        'periodo_seleccionado': period,
        'ultima_actualizacion': timezone.localtime(),
        'summary': summary,
        'item_count': len(summary['items']),
        'umbral_delegacion': umbral_delegacion(period),
        'clasificacion_umbral': clasificar_umbral(
            summary['avance_real'], tiene_items=has_items,
            umbral=umbral_delegacion(period),
        ),
    })


@cargo_required('coordinador', 'admin', 'administrador',permission='request_closed_period_authorization')
def solicitudes_autorizacion(request):
    """
    Permite a Coordinación crear nuevas solicitudes de autorización para operar sobre períodos cerrados o cancelar solicitudes pendientes,
    registrando cada acción en el historial.
    """
    if request.method == 'POST':
        if request.POST.get('action') == 'cancelar':
            solicitud = get_object_or_404(SolicitudAutorizacionPeriodo,pk=request.POST.get('solicitud_id'),vecino__email__iexact=request.user.email,estado=SolicitudAutorizacionPeriodo.Estado.PENDIENTE)
            before = _authorization_snapshot(solicitud)
            solicitud.estado = SolicitudAutorizacionPeriodo.Estado.CANCELADA
            solicitud.decidida_en = timezone.now()
            solicitud.save(update_fields=['estado', 'decidida_en'])
            registrar_historial(actor=request.user,action='Cancelar solicitud de autorización',entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}',before=before,after=_authorization_snapshot(solicitud),period=solicitud.periodo)
            messages.success(request, 'La solicitud fue cancelada.')
            return redirect('coordinador:solicitudes_autorizacion')
        form = AuthorizationRequestForm(request.POST)
        if form.is_valid():
            vecino = Vecino.objects.filter(
                email__iexact=request.user.email,
            ).first()
            if vecino is None:
                form.add_error(
                    None,
                    'No existe un vecino asociado al correo del usuario autenticado.',
                )
            else:
                solicitud = form.save(commit=False)
                solicitud.vecino = vecino
                solicitud.alcances = ['metas']
                solicitud.save()
                form.save_m2m()
                registrar_historial(actor=request.user,action='Solicitar autorización de período',entity=f'SolicitudAutorizacionPeriodo:{solicitud.pk}',after=_authorization_snapshot(solicitud),period=solicitud.periodo)
                messages.success(request, 'La solicitud quedó pendiente de revisión.')
                return redirect('coordinador:solicitudes_autorizacion')
    else:
        form = AuthorizationRequestForm()
    solicitudes = SolicitudAutorizacionPeriodo.objects.filter(vecino__email__iexact=request.user.email).select_related('periodo', 'vecino').prefetch_related('funcionarios')
    return render(request, 'CoordinadorApp/solicitudes_autorizacion.html', {
        'sgr_role': 'Coordinación',
        'form': form,
        'solicitudes': solicitudes,
        'sidebar_modules': _coordinator_management_modules(),
    })


@cargo_required('coordinador', 'admin', 'administrador',permission='manage_coordinator_goals')
def metas(request):
    """
    Delega al mantenedor genérico la gestión global de metas,
    aplicando protección contra edición en períodos cerrados y advertencias sobre la suma total de ponderaciones.
    """
    return maintainer(request,'metas',route_name='coordinador:metas',sgr_role='Coordinación',sidebar_modules=_coordinator_management_modules(),
        protect_closed_periods=True,global_scope=True,coordinator_meta_delete=True,
        warn_weight_total=True,
        closed_period_authorization=True,
    )


@cargo_required('coordinador', 'admin', 'administrador',permission='manage_coordinator_position_functions')
def cargos_funciones(request):
    """
    Delega al mantenedor genérico la administración global de la asignación de funciones asociadas a cada cargo dentro del sistema.
    """
    return maintainer(request,'cargos-funciones',route_name='coordinador:cargos_funciones',sgr_role='Coordinación',sidebar_modules=_coordinator_management_modules(),global_scope=True)


@cargo_required('coordinador', 'admin', 'administrador',permission='view_coordinator_weights')
def ponderaciones(request):
    """
    Agrupa los desempeños por período y funcionario para calcular y validar la suma porcentual de sus ponderaciones
    (incompleta, cumple 100 % o excede 100 %).
    """
    period_id = request.GET.get('periodo', '')
    cargo_id = request.GET.get('cargo', '')
    user_id = request.GET.get('funcionario', '')
    queryset = Desempeno.objects.select_related('item', 'periodo', 'usuario',).order_by('periodo__fecha_inicio', 'usuario__email', 'item__nombre')
    if period_id.isdecimal():
        queryset = queryset.filter(periodo_id=period_id)
    if cargo_id.isdecimal():
        queryset = queryset.filter(usuario__usuariocargo__cargo_id=cargo_id,usuario__usuariocargo__fecha_fin__isnull=True,).distinct()
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

        ponderacion_val = getattr(record, 'ponderacion', None)
        if ponderacion_val is None and record.item:
            ponderacion_val = getattr(record.item, 'ponderacion', Decimal('0'))

        grouped[key]['total'] += ponderacion_val or Decimal('0')

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
        'funcionarios': get_user_model().objects.filter(is_active=True,).order_by('last_name', 'first_name', 'email'),
        'selected_period': period_id,
        'selected_cargo': cargo_id,
        'selected_user': user_id,
    })


def _report_filters(request):
    """
    Extrae y resuelve los parámetros de filtrado desde la petición HTTP
    (período activo o seleccionado, delegación, cargo y funcionario) para los reportes.
    """
    periods = Periodo.objects.order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    if period_id.isdecimal():
        period = periods.filter(pk=period_id).first()
    else:
        period = (
            periodo_vigente(periods.filter(estado=Periodo.Estado.ABIERTO))
            or periodo_vigente(periods)
        )
    delegation_id = request.GET.get('delegacion', '')
    cargo_id = request.GET.get('cargo', '')
    user_id = request.GET.get('funcionario', '')
    return periods, period, period_id, delegation_id, cargo_id, user_id


def consolidated_report_rows(request):
    """
    Consolida los indicadores de avance real, clasificación por umbral y 
    distribución semafórica a nivel individual y agregado por delegación.
    """
    periods, period, period_id, delegation_id, cargo_id, user_id = _report_filters(request)
    rules = parametros_periodo(period)
    cap = rules['tope']
    threshold = rules['delegacion']
    users = get_user_model().objects.filter(
        is_active=True,
    ).order_by('last_name', 'first_name', 'email')
    if delegation_id.isdecimal():
        users = users.filter(usuariodelegacion__delegacion_id=delegation_id,usuariodelegacion__fecha_fin__isnull=True,).distinct()
    if cargo_id.isdecimal():
        users = users.filter(usuariocargo__cargo_id=cargo_id,usuariocargo__fecha_fin__isnull=True,).distinct()
    if user_id.isdecimal():
        users = users.filter(pk=user_id)
    users = list(users)
    user_ids = {user.pk for user in users}
    performances = Desempeno.objects.none()
    if period and user_ids:
        performances = Desempeno.objects.filter(periodo=period, usuario_id__in=user_ids,).select_related('item', 'periodo', 'usuario')
    performances = list(performances)
    counts = {
        (row['autor_id'], row['item_id'], row['periodo_id']): row['cantidad']
        for row in Registro.objects.filter(autor_id__in=user_ids,periodo_id=period.pk if period else None,estado=Registro.Estado.VALIDADA,
            evidencia__estado=Evidencia.Estado.APROBADA,
        ).values('autor_id', 'item_id', 'periodo_id').annotate(
            cantidad=Count('pk', distinct=True),)
    
    } if period and user_ids else {}
    performances_by_user = defaultdict(list)
    for performance in performances:
        performances_by_user[performance.usuario_id].append(performance)
    rows = []
    summaries = defaultdict(lambda: {
        'delegacion': '', 'cargo': '', 'total_avance_real': ZERO,
        'con_items': 0, 'sobre': 0, 'bajo': 0, 'sin_items': 0,
        'user_summaries': [],
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
        # El consolidado es único por delegación; el cargo solo filtra el
        # conjunto de funcionarios antes de aplicar la fórmula común.
        group = summaries[delegation]
        group['delegacion'] = delegation
        group['cargo'] = 'Todos los cargos'
        group['user_summaries'].append(summary)
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
        collective = consolidar_cumplimientos(group.pop('user_summaries'),threshold=threshold)
        group.update(collective)
        group['promedio_avance_real'] = collective['cumplimiento_colectivo']
        group['verde'] = collective['distribucion_semaforo']['verde']['count']
        group['ambar'] = collective['distribucion_semaforo']['ambar']['count']
        group['rojo'] = collective['distribucion_semaforo']['rojo']['count']
        group['sin_items'] = collective['distribucion_semaforo']['sin_items']['count']
    return periods, period, period_id or (str(period.pk) if period else ''), delegation_id, cargo_id, user_id, rows, list(summaries.values())


@cargo_required('coordinador', 'admin', 'administrador', permission='view_coordinator_reports')
def informes(request):
    """
    Genera la vista paginada del informe consolidado de cumplimiento y
    gestiona su exportación en formatos CSV, Excel o PDF con registro de auditoría.
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    data = consolidated_report_rows(request)
    periods, period, period_id, delegation_id, cargo_id, user_id, rows, summaries = data
    export_fmt = request.GET.get('export')
    if export_fmt in {'csv', 'excel', 'pdf'}:
        selected_delegation_obj = (Delegacion.objects.filter(pk=delegation_id).first()
            if delegation_id.isdecimal()
            else 'Todas las delegaciones'
        )
        exporter = {'excel': excel_rows_response, 'pdf': pdf_rows_response}.get(export_fmt, csv_response)
        ext = {'excel': 'xlsx', 'pdf': 'pdf'}.get(export_fmt, 'csv')
        return exporter(request,filename=f'informe_consolidado.{ext}',rows=consolidated_report_csv_rows(period, rows, summaries),
            entity='InformeConsolidado',
            action=f'Exportar informe consolidado {ext.upper()}',
            title='Informe consolidado de cumplimiento',
            delegation=selected_delegation_obj,
            filters={
                'periodo': period_id,
                'delegacion': delegation_id,
                'cargo': cargo_id,
                'funcionario': user_id,
            },
            row_count=len(rows),period=period)
    
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
        'ultima_actualizacion': timezone.localtime(),
    })


def _trend_range(raw_value):
    """
    Valida y normaliza el parámetro numérico de cantidad de períodos a consultar en las tendencias históricas,
    acotándolo entre 1 y 12 (6 por defecto).
    """
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
    """
    Valida que los identificadores recibidos por parámetro
    correspondan a enteros positivos dentro del rango permitido por la base de datos.
    """
    if raw_value in (None, ''):
        return None, ''
    if not raw_value.isdecimal():
        return None, f'El identificador de {label} no es válido; no hay resultados para ese filtro.'
    normalized = raw_value.lstrip('0')
    if (not normalized or len(normalized) > 19 or (len(normalized) == 19 and normalized > '9223372036854775807')):
        return None, f'El identificador de {label} no es válido; no hay resultados para ese filtro.'
    return int(normalized), ''


def _trend_chart(series, threshold):
    """
    Calcula las coordenadas cartesianas (ejes X e Y), 
    marcas de escala y la línea base del umbral para graficar la evolución histórica de cumplimiento.
    """
    points = [row for row in series if row['funcionarios_considerados']]
    if len(points) < 2:
        return [], [], 100, 0

    max_value = max(max(row['promedio_avance_real'], row['porcentaje_sobre_umbral']) for row in points)
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
            'esperado_y': round(bottom - float(row['promedio_esperado']) * plot_height / chart_max),
            'sobre_y': round(bottom - float(row['porcentaje_sobre_umbral']) * plot_height / chart_max),
        })
    ticks = [
        {'value': value, 'y': round(bottom - value * plot_height / chart_max)}
        for value in range(0, chart_max + 1, 25)
    ]
    threshold_y = round(bottom - float(threshold) * plot_height / chart_max)
    return chart_points, ticks, chart_max, threshold_y


@cargo_required('coordinador', 'admin', 'administrador',permission='view_coordinator_trends')
def tendencias(request):
    """
    Construye el análisis evolutivo del cumplimiento a través de múltiples períodos filtrados por delegación,
    cargo o funcionario, permitiendo su visualización gráfica y exportación.
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])

    period_limit, range_message = _trend_range(request.GET.get('periodos', ''))
    selected_periods = list(Periodo.objects.order_by('-fecha_inicio', '-pk')[:period_limit])
    selected_periods.reverse()

    raw_filters = {'delegacion': request.GET.get('delegacion', ''),'cargo': request.GET.get('cargo', ''),
        'funcionario': request.GET.get('funcionario', ''),}
    
    parsed_filters = {}
    filter_message = ''
    for key, label in (('delegacion', 'delegación'),('cargo', 'cargo'),('funcionario', 'funcionario'),):
        parsed_filters[key], error = _trend_filter_id(raw_filters[key], label)
        if error and not filter_message:
            filter_message = error

    User = get_user_model()
    filter_models = {'delegacion': Delegacion,'cargo': Cargo,'funcionario': User}
    filter_labels = {'delegacion': 'delegación','cargo': 'cargo','funcionario': 'funcionario'}
    for key, value in parsed_filters.items():
        if value is not None and not filter_models[key].objects.filter(pk=value).exists():
            filter_message = (
                f'No existe la opción seleccionada para el filtro de '
                f'{filter_labels[key]}; no hay resultados.'
            )
            break

    users = User.objects.filter(is_active=True,).order_by('last_name', 'first_name', 'email')
    if parsed_filters['delegacion'] is not None:
        users = users.filter(usuariodelegacion__delegacion_id=parsed_filters['delegacion'],usuariodelegacion__fecha_fin__isnull=True,).distinct()
    if parsed_filters['cargo'] is not None:
        users = users.filter(usuariocargo__cargo_id=parsed_filters['cargo'],usuariocargo__fecha_fin__isnull=True,).distinct()
    if parsed_filters['funcionario'] is not None:
        users = users.filter(pk=parsed_filters['funcionario'])
    users = list(users) if not filter_message else []

    threshold = umbral_delegacion(selected_periods[0] if selected_periods else None)
    series = tendencias_cumplimiento(users,selected_periods,cap=None,umbral=threshold)
    chart_points, chart_ticks, chart_max, threshold_y = _trend_chart(series,threshold)

    if filter_message:
        empty_message = filter_message
    elif not users:
        empty_message = 'No hay funcionarios activos que coincidan con los filtros seleccionados.'
    elif not selected_periods:
        empty_message = 'No hay períodos configurados para mostrar.'
    else:
        empty_message = ''

    export_fmt = request.GET.get('export')
    if export_fmt in {'csv', 'excel', 'pdf'}:
        selected_delegation_obj = (Delegacion.objects.filter(pk=parsed_filters['delegacion']).first() 
            if parsed_filters.get('delegacion')
            else 'Todas las delegaciones')
        
        exporter = {'excel': excel_rows_response, 'pdf': pdf_rows_response}.get(export_fmt, csv_response)
        ext = {'excel': 'xlsx', 'pdf': 'pdf'}.get(export_fmt, 'csv')
        return exporter(request,filename=f'tendencias_historicas.{ext}',
            rows=[[
                'Período',
                'Funcionarios considerados',
                'Promedio de avance real (%)',
                'Funcionarios sobre el umbral (%)',
                'Funcionarios sin ítems',]] + 
            [[
                item['periodo'].nombre,
                item['funcionarios_considerados'],
                item['promedio_avance_real'],
                item['porcentaje_sobre_umbral'],
                item['funcionarios_sin_items'],
            ] for item in series],entity='TendenciasHistoricas',action=f'Exportar tendencias históricas {ext.upper()}',
            title='Reporte de tendencias históricas',
            delegation=selected_delegation_obj,
            filters={**raw_filters, 'periodos': period_limit},
            row_count=len(series),
            period=selected_periods[-1] if selected_periods else None,
        )
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
        'funcionarios': User.objects.filter(is_active=True,).order_by('last_name', 'first_name', 'email'),
        'selected_delegation': raw_filters['delegacion'],
        'selected_cargo': raw_filters['cargo'],
        'selected_user': raw_filters['funcionario'],
        'chart_points': chart_points,
        'chart_ticks': chart_ticks,
        'chart_max': chart_max,
        'threshold': threshold,
        'threshold_y': threshold_y,
    })
