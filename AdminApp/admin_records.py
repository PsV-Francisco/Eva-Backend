import json
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from AdminApp.csv_utils import csv_response
from AdminApp.delegation_scope import (
    available_delegations,
    filter_by_delegation,
    selected_delegation,
)
from AdminApp.models import Cargo, Delegacion
from AdminApp.roles import is_system_administrator
from config.decorators import cargo_required
from CoordinadorApp.models import AtencionSocial, Periodo
from CoordinadorApp.reporting import consolidated_report_csv_rows
from DelegadoApp.models import (
    Ausencia,
    Compromiso,
    Felicitacion,
    Hito,
    Informe,
    Reclamo,
)
from FuncionarioApp.models import JuntaVecino, Registro, Vecino


@dataclass(frozen=True)
class RecordListSpec:
    key: str
    title: str
    permission: str
    model: type
    columns: tuple
    search_fields: tuple
    delegation_lookup: str
    assignment_lookup: str = ''
    select_related: tuple = ()
    numeric_search_fields: tuple = ()
    create_route: str = ''
    edit_route: str = ''
    delete_route: str = ''
    status_field: str = ''


LIST_SPECS = {
    'ausencias': RecordListSpec(
        key='ausencias',
        title='Ausencias',
        permission='access_admin_absences',
        model=Ausencia,
        columns=(
            ('Fecha', 'fecha'),
            ('Funcionario', 'desempeno__usuario__email'),
            ('Ítem', 'item__nombre'),
            ('Período', 'periodo__nombre'),
            ('Descripción', 'descripcion'),
        ),
        search_fields=(
            'descripcion',
            'desempeno__usuario__email',
            'item__nombre',
            'periodo__nombre',
        ),
        delegation_lookup='desempeno__usuario__usuariodelegacion__delegacion_id',
        assignment_lookup='desempeno__usuario__usuariodelegacion',
        select_related=('desempeno__usuario', 'item', 'periodo'),
    ),
    'felicitaciones': RecordListSpec(
        key='felicitaciones',
        title='Felicitaciones',
        permission='access_admin_congratulations',
        model=Felicitacion,
        columns=(
            ('Fecha', 'fecha'),
            ('Funcionario', 'desempeno__usuario__email'),
            ('Ítem', 'item__nombre'),
            ('Período', 'periodo__nombre'),
            ('Ubicación', 'ubicacion'),
            ('Estado', 'estado'),
        ),
        search_fields=(
            'ubicacion',
            'estado',
            'desempeno__usuario__email',
            'item__nombre',
            'periodo__nombre',
        ),
        delegation_lookup='desempeno__usuario__usuariodelegacion__delegacion_id',
        assignment_lookup='desempeno__usuario__usuariodelegacion',
        select_related=('desempeno__usuario', 'item', 'periodo'),
    ),
    'reclamos': RecordListSpec(
        key='reclamos',
        title='Reclamos',
        permission='access_admin_complaints',
        model=Reclamo,
        columns=(
            ('Fecha', 'fecha'),
            ('Funcionario', 'desempeno__usuario__email'),
            ('Ítem', 'item__nombre'),
            ('Período', 'periodo__nombre'),
            ('Ubicación', 'ubicacion'),
            ('Estado', 'estado'),
        ),
        search_fields=(
            'evidencia',
            'ubicacion',
            'estado',
            'desempeno__usuario__email',
            'item__nombre',
            'periodo__nombre',
        ),
        delegation_lookup='desempeno__usuario__usuariodelegacion__delegacion_id',
        assignment_lookup='desempeno__usuario__usuariodelegacion',
        select_related=('desempeno__usuario', 'item', 'periodo'),
    ),
    'hitos': RecordListSpec(
        key='hitos',
        title='Hitos',
        permission='access_admin_milestones',
        model=Hito,
        columns=(
            ('Hito', 'nombre'),
            ('Fecha de término', 'fecha_termino'),
            ('Delegación', 'delegacion__nombre'),
            ('Territorio', 'territorio__nombre'),
            ('Responsable', 'responsable__email'),
            ('Estado', 'estado'),
        ),
        search_fields=(
            'nombre',
            'descripcion',
            'delegacion__nombre',
            'territorio__nombre',
            'responsable__email',
            'estado',
        ),
        delegation_lookup='delegacion_id',
        select_related=('delegacion', 'territorio', 'responsable'),
    ),
    'vecinos': RecordListSpec(
        key='vecinos',
        title='Vecinos',
        permission='access_admin_neighbors',
        model=Vecino,
        columns=(
            ('Nombre', 'nombre'),
            ('Teléfono', 'telefono'),
            ('Delegación', 'delegacion__nombre'),
            ('Territorio', 'territorio__nombre'),
            ('Junta', 'junta_vecino__nombre'),
            ('Estado', 'activo'),
        ),
        search_fields=(
            'nombre',
            'telefono',
            'direccion',
            'delegacion__nombre',
            'territorio__nombre',
            'junta_vecino__nombre',
        ),
        delegation_lookup='delegacion_id',
        select_related=(
            'delegacion',
            'territorio',
            'junta_vecino',
        ),
        create_route='administracion:vecino-nuevo',
        edit_route='administracion:vecino-editar',
        delete_route='administracion:vecino-eliminar',
        status_field='activo',
    ),
    'juntas': RecordListSpec(
        key='juntas',
        title='Juntas de Vecinos',
        permission='access_admin_neighborhood_associations',
        model=JuntaVecino,
        columns=(
            ('Nombre', 'nombre'),
            ('Delegación', 'delegacion__nombre'),
            ('Territorio', 'territorio__nombre'),
            ('Domicilio legal', 'domicilio_legal'),
            ('Número de personalidad jurídica', 'numero_rpj'),
            ('Socios activos', 'socios_activos'),
        ),
        search_fields=(
            'nombre',
            'domicilio_legal',
            'territorio__nombre',
            'delegacion__nombre',
        ),
        delegation_lookup='delegacion_id',
        select_related=('delegacion', 'territorio'),
        numeric_search_fields=('numero_rpj', 'numero_registro'),
        create_route='administracion:junta-nueva',
        edit_route='administracion:junta-editar',
        delete_route='administracion:junta-eliminar',
    ),
    'registros': RecordListSpec(
        key='registros',
        title='Registros',
        permission='access_admin_records',
        model=Registro,
        columns=(
            ('Fecha', 'fecha'),
            ('Funcionario', 'autor__email'),
            ('Ítem', 'item__nombre'),
            ('Período', 'periodo__nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        search_fields=(
            'autor__email',
            'item__nombre',
            'periodo__nombre',
            'descripcion',
            'estado',
        ),
        delegation_lookup='autor__usuariodelegacion__delegacion_id',
        assignment_lookup='autor__usuariodelegacion',
        select_related=('autor', 'item', 'periodo'),
    ),
    'atenciones-sociales': RecordListSpec(
        key='atenciones-sociales',
        title='Atenciones Sociales',
        permission='access_admin_social_attentions',
        model=AtencionSocial,
        columns=(
            ('Fecha', 'fecha'),
            ('Autor', 'autor__email'),
            ('Beneficiado', 'beneficiado__nombre'),
            ('Tipo', 'tipo__nombre'),
            ('Subtipo', 'subtipo__nombre'),
            ('Gestión', 'gestion_atencion__numero_gestion'),
            ('Resultado', 'resultado'),
        ),
        search_fields=(
            'autor__email',
            'beneficiado__nombre',
            'beneficiado__apellido',
            'tipo__nombre',
            'subtipo__nombre',
            'resultado',
            'observaciones',
        ),
        delegation_lookup='autor__usuariodelegacion__delegacion_id',
        assignment_lookup='autor__usuariodelegacion',
        select_related=(
            'autor',
            'beneficiado',
            'tipo',
            'subtipo',
            'gestion_atencion',
        ),
    ),
    'compromisos': RecordListSpec(
        key='compromisos',
        title='Compromisos',
        permission='access_admin_commitments',
        model=Compromiso,
        columns=(
            ('Fecha', 'fecha'),
            ('Delegación', 'agenda__delegacion__nombre'),
            ('Período', 'agenda__periodo__nombre'),
            ('Descripción', 'descripcion'),
            ('Solicitante', 'solicitante'),
            ('Territorio', 'territorio'),
            ('Estado', 'estado'),
        ),
        search_fields=(
            'descripcion',
            'solicitante',
            'territorio',
            'estado',
            'agenda__delegacion__nombre',
            'agenda__periodo__nombre',
            'tipo__nombre',
            'subtipo__nombre',
        ),
        delegation_lookup='agenda__delegacion_id',
        select_related=(
            'agenda__delegacion',
            'agenda__periodo',
            'tipo',
            'subtipo',
        ),
    ),
}


def _column_value(record, field):
    value = record
    for part in field.split('__'):
        value = getattr(value, part, None)
        if value is None:
            return ''
    if isinstance(value, bool):
        return 'Activo' if value else 'Inactivo'
    return value


def _search_queryset(queryset, fields, numeric_fields, query):
    if not query:
        return queryset
    search = Q()
    for field in fields:
        search |= Q(**{f'{field}__icontains': query})
    if query.isdecimal() and len(query) <= 9:
        for field in numeric_fields:
            search |= Q(**{field: int(query)})
    return queryset.filter(search)


def _record_list(request, spec):
    export = request.GET.get('export', '')
    if export not in {'', 'csv'}:
        return HttpResponseBadRequest('Formato de exportación no válido.')

    queryset = spec.model.objects.select_related(*spec.select_related)
    queryset = filter_by_delegation(
        queryset,
        request,
        delegation_lookup=spec.delegation_lookup,
        assignment_lookup=spec.assignment_lookup or None,
    )
    query = request.GET.get('q', '').strip()
    queryset = _search_queryset(
        queryset,
        spec.search_fields,
        spec.numeric_search_fields,
        query,
    )

    show_inactive = request.GET.get('inactivos') == '1'
    if spec.status_field and not show_inactive:
        queryset = queryset.filter(**{spec.status_field: True})

    ordering = spec.model._meta.ordering or ('pk',)
    queryset = queryset.order_by(*ordering).distinct()
    headers = [label for label, _ in spec.columns]
    filters = {
        key: value
        for key, value in request.GET.items()
        if key not in {'page', 'export'}
    }

    if export == 'csv':
        rows = [headers]
        rows.extend(
            [_column_value(record, field) for _, field in spec.columns]
            for record in queryset
        )
        return csv_response(
            request,
            filename=f'{spec.key}.csv',
            rows=rows,
            entity=f'Listado:{spec.key}',
            filters=filters,
            row_count=queryset.count(),
        )

    page_obj = Paginator(queryset, 20).get_page(request.GET.get('page'))
    page_rows = [
        {
            'object': record,
            'values': [
                _column_value(record, field)
                for _, field in spec.columns
            ],
        }
        for record in page_obj.object_list
    ]
    delegation = selected_delegation(request)
    selected_delegation_value = (
        str(delegation.pk) if delegation
        else 'todas' if is_system_administrator(request.user)
        else ''
    )
    pagination_parameters = request.GET.copy()
    pagination_parameters.pop('page', None)
    pagination_parameters.pop('export', None)
    return render(request, 'AdminApp/records.html', {
        'title': spec.title,
        'spec': spec,
        'columns': headers,
        'page_obj': page_obj,
        'rows': page_rows,
        'query': query,
        'show_inactive': show_inactive,
        'delegaciones': available_delegations(request.user),
        'selected_delegation': selected_delegation_value,
        'is_administrator': is_system_administrator(request.user),
        'pagination_query': pagination_parameters.urlencode(),
    })


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_absences')
def ausencias(request):
    return _record_list(request, LIST_SPECS['ausencias'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_congratulations')
def felicitaciones(request):
    return _record_list(request, LIST_SPECS['felicitaciones'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_complaints')
def reclamos(request):
    return _record_list(request, LIST_SPECS['reclamos'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_milestones')
def hitos(request):
    return _record_list(request, LIST_SPECS['hitos'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_neighbors')
def vecinos(request):
    return _record_list(request, LIST_SPECS['vecinos'])


@cargo_required(
    'admin',
    'administrador',
    permission='access_admin_neighborhood_associations',
)
@require_GET
def juntas(request):
    return _record_list(request, LIST_SPECS['juntas'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_generated_reports')
def informes_generados(request):
    from CoordinadorApp.views import consolidated_report_rows

    data = consolidated_report_rows(request)
    periods, period, period_id, delegation_id, cargo_id, user_id, rows, summaries = data
    if request.GET.get('export') == 'csv':
        filters = {
            'periodo': period_id,
            'delegacion': delegation_id,
            'cargo': cargo_id,
            'funcionario': user_id,
        }
        persisted_filters = {
            key: value[:32] if value.isdecimal() else ''
            for key, value in filters.items()
        }
        with transaction.atomic():
            Informe.objects.create(
                tipo='informe_consolidado',
                filtros=json.dumps(
                    persisted_filters,
                    ensure_ascii=False,
                    separators=(',', ':'),
                ),
                fecha_generacion=timezone.now(),
                formato='csv',
                autor=request.user,
            )
            return csv_response(
                request,
                filename='informe_consolidado.csv',
                rows=consolidated_report_csv_rows(period, rows, summaries),
                entity='InformeConsolidado',
                action='Exportar informe consolidado CSV',
                filters=filters,
                row_count=len(rows),
                period=period,
            )

    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'CoordinadorApp/informes.html', {
        'sgr_role': 'Administrador',
        'sidebar_modules': (),
        'page_obj': page,
        'summaries': summaries,
        'periodos': periods,
        'delegaciones': Delegacion.objects.order_by('nombre'),
        'cargos': Cargo.objects.filter(
            estado=Cargo.Estado.ACTIVO,
        ).order_by('nombre'),
        'funcionarios': get_user_model().objects.filter(
            is_active=True,
        ).order_by('last_name', 'first_name', 'email'),
        'selected_period': period_id,
        'selected_delegation': delegation_id,
        'selected_cargo': cargo_id,
        'selected_user': user_id,
        'periodo_seleccionado': period,
    })


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_delegation_summary')
def resumen_delegacion(request):
    from DelegadoApp.services import resumen_delegacion as build_summary

    period_id = request.GET.get('periodo', '')
    period = (
        Periodo.objects.filter(pk=int(period_id)).first()
        if period_id.isdecimal()
        else Periodo.objects.filter(
            estado=Periodo.Estado.ABIERTO,
        ).order_by('-fecha_inicio').first()
    )
    delegation = selected_delegation(request)
    result = build_summary(
        delegation=delegation,
        period=period,
        all_delegations=delegation is None,
    )
    selected_delegation_value = (
        str(delegation.pk) if delegation else 'todas'
    )
    if request.GET.get('export') == 'csv':
        rows = [[
            'Funcionario',
            'Correo',
            'Cumplimiento',
            'Esperado',
            'Semáforo',
            'Último registro',
            'Fecha del último registro',
        ]]
        rows.extend([
            row['usuario'].get_full_name() or row['usuario'].email,
            row['usuario'].email,
            row['cumplimiento'],
            row['esperado'],
            row['semaforo'],
            row['ultimo_registro'] or '',
            row['fecha_ultimo_registro'] or '',
        ] for row in result['funcionarios'])
        return csv_response(
            request,
            filename='resumen_delegacion.csv',
            rows=rows,
            entity='ResumenDelegacion',
            action='Exportar resumen de delegación CSV',
            filters={
                'delegacion': selected_delegation_value,
                'periodo': str(period.pk) if period else '',
            },
            row_count=len(result['funcionarios']),
            period=period,
        )

    return render(request, 'DelegadoApp/resumen.html', {
        'sgr_role': 'Administrador',
        'sidebar_modules': (),
        'periodos': Periodo.objects.order_by('-fecha_inicio'),
        'periodo_seleccionado': period,
        'delegaciones': available_delegations(request.user),
        'selected_delegation': selected_delegation_value,
        'delegacion_nombre': (
            delegation.nombre if delegation else 'Todas las delegaciones'
        ),
        'is_administrator': True,
        **result,
    })


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_records')
def registros(request):
    return _record_list(request, LIST_SPECS['registros'])


@require_GET
@cargo_required(
    'admin',
    'administrador',
    permission='access_admin_social_attentions',
)
def atenciones_sociales(request):
    return _record_list(request, LIST_SPECS['atenciones-sociales'])


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_commitments')
def compromisos(request):
    return _record_list(request, LIST_SPECS['compromisos'])


@cargo_required('admin', 'administrador', permission='create_admin_neighbors')
def vecino_nuevo(request):
    from FuncionarioApp.views import _vecino_form

    return _vecino_form(
        request,
        return_url_name='administracion:vecinos',
        sidebar_modules=(),
        sgr_role='Administrador',
    )


@cargo_required('admin', 'administrador', permission='edit_admin_neighbors')
def vecino_editar(request, vecino_id):
    from FuncionarioApp.views import _vecino_form

    return _vecino_form(
        request,
        vecino_id,
        return_url_name='administracion:vecinos',
        sidebar_modules=(),
        sgr_role='Administrador',
    )


@cargo_required('admin', 'administrador', permission='delete_admin_neighbors')
@require_POST
def vecino_eliminar(request, vecino_id):
    from FuncionarioApp.views import eliminar_vecino

    return eliminar_vecino(
        request,
        vecino_id,
        return_url_name='administracion:vecinos',
    )


@cargo_required(
    'admin',
    'administrador',
    permission='create_admin_juntas',
)
def junta_nueva(request):
    from FuncionarioApp.views import _junta_form

    return _junta_form(
        request,
        return_url_name='administracion:juntas',
        sidebar_modules=(),
        sgr_role='Administrador',
    )


@cargo_required(
    'admin',
    'administrador',
    permission='edit_admin_juntas',
)
def junta_editar(request, junta_id):
    from FuncionarioApp.views import _junta_form

    return _junta_form(
        request,
        junta_id,
        return_url_name='administracion:juntas',
        sidebar_modules=(),
        sgr_role='Administrador',
    )


@cargo_required(
    'admin',
    'administrador',
    permission='delete_admin_juntas',
)
@require_POST
def junta_eliminar(request, junta_id):
    from FuncionarioApp.views import eliminar_junta

    return eliminar_junta(
        request,
        junta_id,
        return_url_name='administracion:juntas',
    )
