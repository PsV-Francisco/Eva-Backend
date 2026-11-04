import json
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from AdminApp.csv_utils import csv_response
from AdminApp.audit import registrar_historial
from AdminApp.delegation_scope import (
    available_delegations,
    filter_by_delegation,
    selected_delegation,
)
from AdminApp.models import Cargo, Delegacion
from AdminApp.roles import is_system_administrator
from AdminApp.record_forms import (
    AdminAtencionSocialForm,
    AdminCompromisoForm,
    AdminRegistroForm,
    AusenciaForm,
    FelicitacionForm,
    HitoForm,
    ReclamoForm,
)
from config.decorators import cargo_required
from CoordinadorApp.models import AtencionSocial, Desempeno, Periodo
from CoordinadorApp.reporting import consolidated_report_csv_rows
from DelegadoApp.models import (
    Agenda,
    Ausencia,
    Compromiso,
    Felicitacion,
    Hito,
    Informe,
    Reclamo,
)
from DelegadoApp.services import actualizar_estado_compromiso
from FuncionarioApp.models import (
    JuntaVecino,
    Registro,
    Territorio,
    Vecino,
)
from SupervisorApp.models import Evidencia


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
        create_route='administracion:ausencia-nueva',
        edit_route='administracion:ausencia-editar',
        delete_route='administracion:ausencia-eliminar',
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
        create_route='administracion:felicitacion-nueva',
        edit_route='administracion:felicitacion-editar',
        delete_route='administracion:felicitacion-eliminar',
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
        create_route='administracion:reclamo-nuevo',
        edit_route='administracion:reclamo-editar',
        delete_route='administracion:reclamo-eliminar',
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
        create_route='administracion:hito-nuevo',
        edit_route='administracion:hito-editar',
        delete_route='administracion:hito-eliminar',
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
        create_route='administracion:registro-nuevo',
        edit_route='administracion:registro-editar',
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
        create_route='administracion:atencion-social-nueva',
        edit_route='administracion:atencion-social-editar',
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
        create_route='administracion:compromiso-nuevo',
        edit_route='administracion:compromiso-editar',
    ),
}


@dataclass(frozen=True)
class RelatedRecordCrudSpec:
    key: str
    title: str
    model: type
    form_class: type
    delegation_lookup: str
    assignment_lookup: str = ''
    performance_form: bool = False


CRUD_SPECS = {
    'felicitaciones': RelatedRecordCrudSpec(
        key='felicitaciones',
        title='Felicitación',
        model=Felicitacion,
        form_class=FelicitacionForm,
        delegation_lookup=(
            'desempeno__usuario__usuariodelegacion__delegacion_id'
        ),
        assignment_lookup='desempeno__usuario__usuariodelegacion',
        performance_form=True,
    ),
    'reclamos': RelatedRecordCrudSpec(
        key='reclamos',
        title='Reclamo',
        model=Reclamo,
        form_class=ReclamoForm,
        delegation_lookup=(
            'desempeno__usuario__usuariodelegacion__delegacion_id'
        ),
        assignment_lookup='desempeno__usuario__usuariodelegacion',
        performance_form=True,
    ),
    'hitos': RelatedRecordCrudSpec(
        key='hitos',
        title='Hito',
        model=Hito,
        form_class=HitoForm,
        delegation_lookup='delegacion_id',
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


def _ausencias_en_alcance(request):
    return filter_by_delegation(
        Ausencia.objects.select_related(
            'desempeno__usuario',
            'desempeno__item',
            'desempeno__periodo',
        ),
        request,
        delegation_lookup='desempeno__usuario__usuariodelegacion__delegacion_id',
        assignment_lookup='desempeno__usuario__usuariodelegacion',
    )


def _desempenos_en_alcance(request):
    return filter_by_delegation(
        Desempeno.objects.select_related('usuario', 'item', 'periodo'),
        request,
        delegation_lookup='usuario__usuariodelegacion__delegacion_id',
        assignment_lookup='usuario__usuariodelegacion',
    )


def _ausencia_snapshot(ausencia):
    return {
        'fecha': ausencia.fecha.isoformat() if ausencia.fecha else None,
        'descripcion': ausencia.descripcion,
        'desempeno_id': ausencia.desempeno_id,
        'usuario_id': ausencia.usuario_id,
        'item_id': ausencia.item_id,
        'periodo_id': ausencia.periodo_id,
    }


def _ausencia_form(request, ausencia_id=None):
    editing = (
        get_object_or_404(_ausencias_en_alcance(request), pk=ausencia_id)
        if ausencia_id is not None else None
    )
    form = AusenciaForm(
        request.POST or None,
        instance=editing,
        desempenos=_desempenos_en_alcance(request).order_by(
            'usuario__email',
            'periodo__nombre',
            'item__nombre',
        ),
    )
    if request.method == 'POST' and form.is_valid():
        before = _ausencia_snapshot(editing) if editing else None
        with transaction.atomic():
            ausencia = form.save()
            registrar_historial(
                actor=request.user,
                action='Editar ausencia' if editing else 'Crear ausencia',
                entity=f'Ausencia:{ausencia.pk}',
                before=before,
                after=_ausencia_snapshot(ausencia),
                period=ausencia.periodo,
            )
        messages.success(
            request,
            'La ausencia se actualizó correctamente.'
            if editing else 'La ausencia se creó correctamente.',
        )
        return redirect(
            f'{reverse("administracion:ausencias")}'
            f'?delegacion={request.GET.get("delegacion", "todas")}',
        )

    return render(request, 'AdminApp/record_form.html', {
        'title': 'Editar ausencia' if editing else 'Crear ausencia',
        'form': form,
        'list_url': reverse('administracion:ausencias'),
        'selected_delegation': request.GET.get('delegacion', 'todas'),
        'delegaciones': available_delegations(request.user),
        'is_administrator': is_system_administrator(request.user),
    })


@cargo_required('admin', 'administrador', permission='create_admin_absences')
def ausencia_nueva(request):
    return _ausencia_form(request)


@cargo_required('admin', 'administrador', permission='edit_admin_absences')
def ausencia_editar(request, ausencia_id):
    return _ausencia_form(request, ausencia_id)


@cargo_required('admin', 'administrador', permission='delete_admin_absences')
@require_POST
def ausencia_eliminar(request, ausencia_id):
    ausencia = get_object_or_404(
        _ausencias_en_alcance(request),
        pk=ausencia_id,
    )
    before = _ausencia_snapshot(ausencia)
    entity = f'Ausencia:{ausencia.pk}'
    try:
        with transaction.atomic():
            ausencia.delete()
            registrar_historial(
                actor=request.user,
                action='Eliminar ausencia',
                entity=entity,
                before=before,
                period=ausencia.periodo,
            )
    except ProtectedError:
        messages.error(
            request,
            'No se puede eliminar la ausencia porque tiene registros asociados.',
        )
    else:
        messages.success(request, 'La ausencia se eliminó correctamente.')
    return redirect(
        f'{reverse("administracion:ausencias")}'
        f'?delegacion={request.GET.get("delegacion", "todas")}',
    )


def _related_record_queryset(spec, request):
    queryset = spec.model.objects.all()
    if spec.key in {'felicitaciones', 'reclamos'}:
        queryset = queryset.select_related(
            'desempeno__usuario',
            'desempeno__item',
            'desempeno__periodo',
        )
    elif spec.key == 'hitos':
        queryset = queryset.select_related(
            'delegacion',
            'territorio',
            'responsable',
            'registro__autor',
            'registro__item',
            'registro__periodo',
        )
    return filter_by_delegation(
        queryset,
        request,
        delegation_lookup=spec.delegation_lookup,
        assignment_lookup=spec.assignment_lookup or None,
    )


def _related_form_kwargs(spec, request):
    if spec.performance_form:
        return {
            'desempenos': _desempenos_en_alcance(request).order_by(
                'usuario__email',
                'periodo__nombre',
                'item__nombre',
            ),
        }

    delegation = selected_delegation(request)
    delegations = available_delegations(request.user)
    if delegation is not None:
        delegations = delegations.filter(pk=delegation.pk)
    territories = Territorio.objects.all()
    records = Registro.objects.filter(
        autor__usuariodelegacion__fecha_fin__isnull=True,
    )
    responsible_users = get_user_model().objects.filter(
        is_active=True,
        usuariocargo__cargo__nombre__iexact='funcionario',
        usuariocargo__fecha_fin__isnull=True,
        usuariodelegacion__fecha_fin__isnull=True,
    )
    if delegation is not None:
        territories = territories.filter(delegacion=delegation)
        records = records.filter(
            autor__usuariodelegacion__delegacion=delegation,
        )
        responsible_users = responsible_users.filter(
            usuariodelegacion__delegacion=delegation,
        )
    return {
        'delegaciones': delegations.order_by('nombre'),
        'territorios': territories.order_by('nombre'),
        'responsables': responsible_users.distinct().order_by(
            'last_name',
            'first_name',
            'email',
        ),
        'registros': records.distinct().select_related(
            'autor',
            'item',
            'periodo',
        ).order_by('-fecha', '-creado'),
    }


def _related_record_snapshot(spec, record):
    snapshot = {}
    for field_name in spec.form_class.Meta.fields:
        field = spec.model._meta.get_field(field_name)
        value = getattr(record, field.attname)
        if hasattr(value, 'isoformat'):
            value = value.isoformat()
        snapshot[field_name] = value
    for field_name in ('usuario', 'item', 'periodo'):
        if hasattr(record, f'{field_name}_id'):
            snapshot[f'{field_name}_id'] = getattr(
                record,
                f'{field_name}_id',
            )
    for field_name in ('autor_registro', 'item_registro', 'periodo_registro'):
        if hasattr(record, field_name):
            snapshot[field_name] = getattr(record, field_name)
    return snapshot


def _related_record_period(record):
    return (
        record.periodo if hasattr(record, 'periodo_id')
        else record.registro.periodo if record.registro_id
        else None
    )


def _related_record_form(request, key, record_id=None):
    spec = CRUD_SPECS[key]
    queryset = _related_record_queryset(spec, request)
    editing = (
        get_object_or_404(queryset, pk=record_id)
        if record_id is not None else None
    )
    form = spec.form_class(
        request.POST or None,
        instance=editing,
        **_related_form_kwargs(spec, request),
    )
    if request.method == 'POST' and form.is_valid():
        before = _related_record_snapshot(spec, editing) if editing else None
        with transaction.atomic():
            record = form.save()
            registrar_historial(
                actor=request.user,
                action=(
                    f'{"Editar" if editing else "Crear"} '
                    f'{spec.title.lower()}'
                ),
                entity=f'{spec.model.__name__}:{record.pk}',
                before=before,
                after=_related_record_snapshot(spec, record),
                period=_related_record_period(record),
            )
        messages.success(
            request,
            f'{spec.title} {"actualizado" if editing else "creado"} correctamente.',
        )
        return redirect(
            f'{reverse(f"administracion:{key}")}'
            f'?delegacion={request.GET.get("delegacion", "todas")}',
        )

    return render(request, 'AdminApp/record_form.html', {
        'title': f'{"Editar" if editing else "Crear"} {spec.title.lower()}',
        'form': form,
        'list_url': reverse(f'administracion:{key}'),
        'selected_delegation': request.GET.get('delegacion', 'todas'),
        'delegaciones': available_delegations(request.user),
        'is_administrator': is_system_administrator(request.user),
    })


def _related_record_delete(request, key, record_id):
    spec = CRUD_SPECS[key]
    record = get_object_or_404(
        _related_record_queryset(spec, request),
        pk=record_id,
    )
    before = _related_record_snapshot(spec, record)
    entity = f'{spec.model.__name__}:{record.pk}'
    period = _related_record_period(record)
    try:
        with transaction.atomic():
            record.delete()
            registrar_historial(
                actor=request.user,
                action=f'Eliminar {spec.title.lower()}',
                entity=entity,
                before=before,
                period=period,
            )
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar el {spec.title.lower()} porque tiene '
            'registros asociados protegidos.',
        )
    else:
        messages.success(
            request,
            f'{spec.title} eliminado correctamente.',
        )
    return redirect(
        f'{reverse(f"administracion:{key}")}'
        f'?delegacion={request.GET.get("delegacion", "todas")}',
    )


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_congratulations')
def felicitaciones(request):
    return _record_list(request, LIST_SPECS['felicitaciones'])


@cargo_required(
    'admin',
    'administrador',
    permission='create_admin_congratulations',
)
def felicitacion_nueva(request):
    return _related_record_form(request, 'felicitaciones')


@cargo_required(
    'admin',
    'administrador',
    permission='edit_admin_congratulations',
)
def felicitacion_editar(request, record_id):
    return _related_record_form(request, 'felicitaciones', record_id)


@cargo_required(
    'admin',
    'administrador',
    permission='delete_admin_congratulations',
)
@require_POST
def felicitacion_eliminar(request, record_id):
    return _related_record_delete(request, 'felicitaciones', record_id)


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_complaints')
def reclamos(request):
    return _record_list(request, LIST_SPECS['reclamos'])


@cargo_required('admin', 'administrador', permission='create_admin_complaints')
def reclamo_nuevo(request):
    return _related_record_form(request, 'reclamos')


@cargo_required('admin', 'administrador', permission='edit_admin_complaints')
def reclamo_editar(request, record_id):
    return _related_record_form(request, 'reclamos', record_id)


@cargo_required('admin', 'administrador', permission='delete_admin_complaints')
@require_POST
def reclamo_eliminar(request, record_id):
    return _related_record_delete(request, 'reclamos', record_id)


@require_GET
@cargo_required('admin', 'administrador', permission='access_admin_milestones')
def hitos(request):
    return _record_list(request, LIST_SPECS['hitos'])


@cargo_required('admin', 'administrador', permission='create_admin_milestones')
def hito_nuevo(request):
    return _related_record_form(request, 'hitos')


@cargo_required('admin', 'administrador', permission='edit_admin_milestones')
def hito_editar(request, record_id):
    return _related_record_form(request, 'hitos', record_id)


@cargo_required('admin', 'administrador', permission='delete_admin_milestones')
@require_POST
def hito_eliminar(request, record_id):
    return _related_record_delete(request, 'hitos', record_id)


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


def _admin_active_functionaries(delegation=None):
    users = get_user_model().objects.filter(
        is_active=True,
        usuariocargo__cargo__nombre__iexact='funcionario',
        usuariocargo__fecha_fin__isnull=True,
        usuariodelegacion__fecha_fin__isnull=True,
    )
    if delegation is not None:
        users = users.filter(usuariodelegacion__delegacion=delegation)
    return users.distinct().order_by('last_name', 'first_name', 'email')


def _selected_delegation_value(request):
    delegation = selected_delegation(request)
    if delegation is not None:
        return str(delegation.pk)
    return 'todas' if is_system_administrator(request.user) else ''


def _record_form_context(request, *, title, form, list_name, editing=None, **extra):
    return {
        'title': title,
        'form': form,
        'list_url': reverse(f'administracion:{list_name}'),
        'selected_delegation': _selected_delegation_value(request),
        'delegaciones': available_delegations(request.user),
        'is_administrator': is_system_administrator(request.user),
        'editing_record': editing,
        **extra,
    }


def _register_snapshot(record):
    return {
        'fecha': record.fecha.isoformat(),
        'periodo_id': record.periodo_id,
        'item_id': record.item_id,
        'autor_id': record.autor_id,
        'descripcion': record.descripcion,
        'accion': record.accion,
        'contacto': record.contacto,
        'telefono': record.telefono,
        'estado': record.estado,
        'evidencias': list(
            record.evidencias_registros.order_by('pk').values_list(
                'pk',
                flat=True,
            ),
        ),
    }


def _registro_en_alcance(request):
    return filter_by_delegation(
        Registro.objects.select_related('autor', 'periodo', 'item'),
        request,
        delegation_lookup='autor__usuariodelegacion__delegacion_id',
        assignment_lookup='autor__usuariodelegacion',
    )


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='create_admin_records',
)
def registro_nuevo(request):
    return _registro_form(request)


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='edit_admin_records',
)
def registro_editar(request, record_id):
    return _registro_form(request, record_id)


def _registro_form(request, record_id=None):
    editing = (
        get_object_or_404(_registro_en_alcance(request), pk=record_id)
        if record_id is not None else None
    )
    before_snapshot = _register_snapshot(editing) if editing else None
    if editing and editing.periodo.estado != Periodo.Estado.ABIERTO:
        messages.error(
            request,
            'No se puede modificar un registro de un período cerrado.',
        )
        return redirect(
            f'{reverse("administracion:registros")}'
            f'?delegacion={_selected_delegation_value(request)}',
        )

    delegation = selected_delegation(request)
    form = AdminRegistroForm(
        request.POST or None,
        request.FILES or None,
        instance=editing,
        user=request.user,
        autores=_admin_active_functionaries(delegation),
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            record = form.save(commit=False)
            record.autor = form.cleaned_data['autor']
            record.save()
            form.save_m2m()
            uploaded_file = form.cleaned_data.get('evidencia')
            if uploaded_file:
                evidence = Evidencia(
                    archivo=uploaded_file,
                    autor=request.user,
                )
                evidence.asignarEvidencia(registro=record)
                evidence.save()
            registrar_historial(
                actor=request.user,
                action='Editar registro' if editing else 'Crear registro',
                entity=f'Registro:{record.pk}',
                before=before_snapshot,
                after=_register_snapshot(record),
                period=record.periodo,
            )
        messages.success(
            request,
            'El registro se actualizó correctamente.'
            if editing else 'El registro se creó correctamente.',
        )
        return redirect(
            f'{reverse("administracion:registros")}'
            f'?delegacion={_selected_delegation_value(request)}',
        )

    return render(
        request,
        'AdminApp/record_form.html',
        _record_form_context(
            request,
            title='Editar registro' if editing else 'Crear registro',
            form=form,
            list_name='registros',
            editing=editing,
        ),
    )


def _atencion_en_alcance(request):
    return filter_by_delegation(
        AtencionSocial.objects.select_related(
            'autor',
            'beneficiado',
            'tipo',
            'subtipo',
            'gestion_atencion',
        ),
        request,
        delegation_lookup='autor__usuariodelegacion__delegacion_id',
        assignment_lookup='autor__usuariodelegacion',
    )


def _atencion_snapshot(atencion):
    return {
        'fecha': atencion.fecha.isoformat(),
        'autor_id': atencion.autor_id,
        'beneficiado_id': atencion.beneficiado_id,
        'tipo_id': atencion.tipo_id,
        'subtipo_id': atencion.subtipo_id,
        'gestion_id': atencion.gestion_atencion_id,
        'numero_gestion': atencion.gestion_atencion.numero_gestion,
        'fecha_gestion': atencion.gestion_atencion.fecha.isoformat(),
        'resultado': atencion.resultado,
        'observaciones': atencion.observaciones,
        'evidencias': list(
            atencion.gestion_atencion.evidencias.order_by('pk').values_list(
                'pk',
                flat=True,
            ),
        ),
    }


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='create_admin_social_attentions',
)
def atencion_social_nueva(request):
    return _atencion_social_form(request)


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='edit_admin_social_attentions',
)
def atencion_social_editar(request, record_id):
    return _atencion_social_form(request, record_id)


def _atencion_social_form(request, record_id=None):
    editing = (
        get_object_or_404(_atencion_en_alcance(request), pk=record_id)
        if record_id is not None else None
    )
    delegation = selected_delegation(request)
    form = AdminAtencionSocialForm(
        request.POST or None,
        request.FILES or None,
        instance=editing,
        autores=_admin_active_functionaries(delegation),
    )
    if request.method == 'POST' and form.is_valid():
        before = _atencion_snapshot(editing) if editing else None
        with transaction.atomic():
            gestion, atencion = form.save(autor=form.cleaned_data['autor'])
            uploaded_file = form.cleaned_data.get('evidencia')
            if uploaded_file:
                evidence = Evidencia(
                    archivo=uploaded_file,
                    autor=request.user,
                )
                evidence.asignarEvidencia(gestion_atencion=gestion)
                evidence.save()
            registrar_historial(
                actor=request.user,
                action=(
                    'Editar atención social'
                    if editing else 'Crear atención social'
                ),
                entity=f'AtencionSocial:{atencion.pk}',
                before=before,
                after=_atencion_snapshot(atencion),
            )
        messages.success(
            request,
            'La atención social se actualizó correctamente.'
            if editing else 'La atención social se creó correctamente.',
        )
        return redirect(
            f'{reverse("administracion:atenciones-sociales")}'
            f'?delegacion={_selected_delegation_value(request)}',
        )

    return render(
        request,
        'AdminApp/record_form.html',
        _record_form_context(
            request,
            title=(
                'Editar atención social'
                if editing else 'Crear atención social'
            ),
            form=form,
            list_name='atenciones-sociales',
            editing=editing,
        ),
    )


def _compromiso_snapshot(compromiso):
    return {
        'agenda_id': compromiso.agenda_id,
        'delegacion_id': compromiso.agenda.delegacion_id,
        'periodo_id': compromiso.agenda.periodo_id,
        'descripcion': compromiso.descripcion,
        'solicitante': compromiso.solicitante,
        'territorio': compromiso.territorio,
        'fecha': compromiso.fecha.isoformat(),
        'estado': compromiso.estado,
        'responsables': list(
            compromiso.responsable.order_by('pk').values_list(
                'pk',
                flat=True,
            ),
        ),
        'evidencias': list(
            compromiso.evidencias_compromiso.order_by('pk').values_list(
                'pk',
                flat=True,
            ),
        ),
    }


def _compromiso_en_alcance(request):
    return filter_by_delegation(
        Compromiso.objects.select_related(
            'agenda__delegacion',
            'agenda__periodo',
        ).prefetch_related('responsable', 'evidencias_compromiso'),
        request,
        delegation_lookup='agenda__delegacion_id',
    )


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='create_admin_commitments',
)
def compromiso_nuevo(request):
    return _compromiso_form(request)


@require_http_methods(['GET', 'POST'])
@cargo_required(
    'admin',
    'administrador',
    permission='edit_admin_commitments',
)
def compromiso_editar(request, record_id):
    return _compromiso_form(request, record_id)


def _compromiso_form(request, record_id=None):
    editing = (
        get_object_or_404(_compromiso_en_alcance(request), pk=record_id)
        if record_id is not None else None
    )
    before_snapshot = _compromiso_snapshot(editing) if editing else None
    original_state = editing.estado if editing else Compromiso.Estado.INGRESADO
    delegation = selected_delegation(request)
    form_delegation = (
        editing.agenda.delegacion if editing and delegation is None
        else delegation
    )
    selected_value = _selected_delegation_value(request)
    list_url = reverse('administracion:compromisos')
    if editing and editing.agenda.periodo.estado != Periodo.Estado.ABIERTO:
        messages.error(
            request,
            'No se puede modificar un compromiso de un período cerrado.',
        )
        return redirect(f'{list_url}?delegacion={selected_value}')
    if editing and editing.evidencias_compromiso.exists():
        messages.error(
            request,
            'No se puede editar un compromiso que ya tiene evidencia asociada.',
        )
        return redirect(f'{list_url}?delegacion={selected_value}')

    responsables = _admin_active_functionaries(form_delegation)
    form = AdminCompromisoForm(
        request.POST or None,
        request.FILES or None,
        instance=editing,
        user=request.user,
        delegation=form_delegation,
        responsables=responsables,
    )
    if editing:
        form.fields['periodo'].disabled = True
        form.fields['periodo'].initial = editing.agenda.periodo_id

    if request.method == 'POST' and not editing and delegation is None:
        messages.error(request, 'Selecciona una delegación para crear el compromiso.')
    elif request.method == 'POST' and form.is_valid():
        desired_state = form.cleaned_data['estado']
        previous_state = original_state
        with transaction.atomic():
            commitment = form.save(commit=False)
            commitment.estado = previous_state
            if editing is None:
                commitment.agenda, _ = Agenda.objects.get_or_create(
                    delegacion=delegation,
                    periodo=form.cleaned_data['periodo'],
                )
            commitment.save()
            form.save_m2m()
            if desired_state != previous_state:
                actualizar_estado_compromiso(
                    compromiso=commitment,
                    autor=request.user,
                    nuevo_estado=desired_state,
                )
            uploaded_file = form.cleaned_data.get('evidencia')
            if uploaded_file:
                evidence = Evidencia(
                    archivo=uploaded_file,
                    autor=request.user,
                )
                evidence.asignarEvidencia(compromiso=commitment)
                evidence.save()
            registrar_historial(
                actor=request.user,
                action=(
                    'Editar compromiso'
                    if editing else 'Crear compromiso'
                ),
                entity=f'Compromiso:{commitment.pk}',
                before=before_snapshot,
                after=_compromiso_snapshot(commitment),
                period=commitment.agenda.periodo,
            )
        messages.success(
            request,
            'El compromiso se actualizó correctamente.'
            if editing else 'El compromiso se creó correctamente.',
        )
        return redirect(f'{list_url}?delegacion={selected_value}')

    return render(
        request,
        'AdminApp/record_form.html',
        _record_form_context(
            request,
            title='Editar compromiso' if editing else 'Crear compromiso',
            form=form,
            list_name='compromisos',
            editing=editing,
            delegation_required=(not editing and delegation is None),
        ),
    )


@cargo_required(
    'admin',
    'administrador',
    permission='manage_admin_goal_adjustments',
)
def ajustes_metas(request):
    from AdminApp.maintainers import maintainer

    return maintainer(
        request,
        'metas',
        route_name='administracion:ajustes-metas',
        sgr_role='Administrador',
        global_scope=True,
        protect_closed_periods=True,
        closed_period_authorization=True,
        update_only=True,
    )


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
