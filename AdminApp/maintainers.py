from dataclasses import dataclass
from io import BytesIO

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from AdminApp.forms import (
    CatalogoForm,
    CargoForm,
    CargoFuncionForm,
    DelegacionForm,
    DesempenoForm,
    FuncionForm,
    ItemForm,
    RolForm,
    SubAtencionForm,
    TipoAtencionForm,
)
from AdminApp.models import (
    Catalogo,
    Cargo,
    Delegacion,
    Rol,
    SubAtencion,
    TipoAtencion,
    is_critical_cargo_name,
)
from AdminApp.roles import (
    ensure_role_group,
    is_system_administrator,
    permission_codenames_for,
)
from CoordinadorApp.models import CargoFuncion, Desempeno, Funcion, Item
from CoordinadorApp.services import authorization_for, record_authorization_use
from config.delegations import active_delegation
from FuncionarioApp.models import AtencionSocial, Registro


@dataclass(frozen=True)
class MaintainerSpec:
    key: str
    title: str
    model: type
    form_class: type
    search_fields: tuple
    display_fields: tuple
    export_fields: tuple
    ordering: tuple
    status_field: str | None = 'estado'
    status_filter_field: str | None = 'estado'
    active_value: object = 'activo'
    inactive_value: object = 'inactivo'


def _delegation_delete_block(delegation):
    if delegation.usuarios.exists() or delegation.usuarios_autorizados.exists():
        return 'La delegación tiene usuarios asociados. Desactívala para conservar esas relaciones.'
    return ''


def _role_delete_block(role):
    if role.protegido:
        return 'Este rol está protegido y no se puede eliminar.'
    if role.usuarios.exists():
        return 'El rol está asignado a usuarios. Desactívalo para conservar esas asignaciones.'
    return ''


def _item_delete_block(item):
    if item.desempenos.exists() or item.registros.exists():
        return 'El ítem tiene metas o registros asociados. Desactívalo para conservarlos.'
    return ''


def _type_delete_block(tipo):
    if tipo.subatenciones.exists():
        return 'El tipo tiene subatenciones asociadas. Desactívalo para conservarlas.'
    if (
        Catalogo.objects.filter(tipo__iexact=tipo.nombre).exists()
        or AtencionSocial.objects.filter(tipo_atencion__iexact=tipo.nombre).exists()
    ):
        return 'El tipo tiene atenciones o catálogos históricos asociados. Desactívalo para conservarlos.'
    return ''


def _subtype_delete_block(subtype):
    if Catalogo.objects.filter(
        tipo__iexact=subtype.tipo_atencion.nombre,
        subtipo__iexact=subtype.nombre,
    ).exists():
        return 'La sub atención tiene catálogos históricos asociados. Desactívala para conservarlos.'
    return ''


def _meta_delete_block(record):
    if record.avance or record.ultimo_registro:
        return 'La meta tiene avance registrado y no se puede eliminar.'
    return ''


def _coordinator_meta_delete_block(record):
    if record.periodo.estado != 'abierto':
        return 'Una meta de un período cerrado no se puede eliminar.'
    if record.avance or record.ultimo_registro:
        return 'La meta tiene avance registrado y no se puede eliminar.'
    activities = Registro.objects.filter(
        autor_id=record.usuario_id,
        item_id=record.item_id,
        periodo_id=record.periodo_id,
    )
    if activities.exists():
        if activities.filter(evidencias_registros__isnull=False).exists():
            return 'La meta tiene actividades y evidencias asociadas; no se puede eliminar.'
        return 'La meta tiene actividades asociadas; no se puede eliminar.'
    return ''


def _cargo_delete_block(cargo):
    if is_critical_cargo_name(cargo.nombre):
        return 'Este cargo se usa en el control de acceso y no se puede eliminar.'
    if cargo.usuarios.exists() or cargo.asignaciones_funciones.exists():
        return 'El cargo tiene usuarios o asignaciones asociadas. Desactívalo para conservarlas.'
    return ''


def _function_delete_block(function):
    if (
        function.items.exists()
        or function.asignaciones_cargos.exists()
        or Cargo.objects.filter(funciones=function).exists()
    ):
        return 'La función tiene ítems o cargos asociados. Desactívala para conservarlos.'
    return ''


def _catalog_delete_block(catalog):
    if catalog.registros_catalogo.exists():
        return 'El catálogo tiene actividades asociadas. Desactívalo para conservarlas.'
    return ''


SPECS = {
    'cargos': MaintainerSpec(
        key='cargos',
        title='Cargos',
        model=Cargo,
        form_class=CargoForm,
        search_fields=('nombre', 'funciones__nombre'),
        display_fields=(
            ('Cargo', 'nombre'),
            ('Función asociada', 'funciones__nombre'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Cargo', 'nombre'),
            ('Función asociada', 'funciones__nombre'),
            ('Estado', 'estado'),
        ),
        ordering=('nombre',),
        active_value=Cargo.Estado.ACTIVO,
        inactive_value=Cargo.Estado.INACTIVO,
    ),
    'funciones': MaintainerSpec(
        key='funciones',
        title='Funciones',
        model=Funcion,
        form_class=FuncionForm,
        search_fields=('nombre', 'descripcion'),
        display_fields=(
            ('Función', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Función', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        ordering=('nombre',),
        active_value=Funcion.Estado.ACTIVO,
        inactive_value=Funcion.Estado.INACTIVO,
    ),
    'cargos-funciones': MaintainerSpec(
        key='cargos-funciones',
        title='Funciones por cargo',
        model=CargoFuncion,
        form_class=CargoFuncionForm,
        search_fields=('cargo__nombre', 'funcion__nombre'),
        display_fields=(
            ('Cargo', 'cargo__nombre'),
            ('Función', 'funcion__nombre'),
        ),
        export_fields=(
            ('Cargo', 'cargo__nombre'),
            ('Función', 'funcion__nombre'),
        ),
        ordering=('cargo__nombre', 'funcion__nombre'),
        status_field=None,
        status_filter_field=None,
    ),
    'catalogo': MaintainerSpec(
        key='catalogo',
        title='Catálogo de actividades',
        model=Catalogo,
        form_class=CatalogoForm,
        search_fields=('actividad', 'servicio', 'tipo', 'subtipo'),
        display_fields=(
            ('Actividad', 'actividad'),
            ('Servicio', 'servicio'),
            ('Tipo', 'tipo'),
            ('Subtipo', 'subtipo'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Actividad', 'actividad'),
            ('Servicio', 'servicio'),
            ('Tipo', 'tipo'),
            ('Subtipo', 'subtipo'),
            ('Estado', 'estado'),
        ),
        ordering=('actividad', 'servicio', 'tipo', 'subtipo'),
        active_value=Catalogo.Estado.ACTIVO,
        inactive_value=Catalogo.Estado.INACTIVO,
    ),
    'delegaciones': MaintainerSpec(
        key='delegaciones',
        title='Delegaciones',
        model=Delegacion,
        form_class=DelegacionForm,
        search_fields=('codigo', 'nombre', 'direccion', 'comuna'),
        display_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Dirección', 'direccion'),
            ('Comuna', 'comuna'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Dirección', 'direccion'),
            ('Comuna', 'comuna'),
            ('Estado', 'estado'),
        ),
        ordering=('nombre',),
        active_value=Delegacion.Estado.ACTIVA,
        inactive_value=Delegacion.Estado.INACTIVA,
    ),
    'roles': MaintainerSpec(
        key='roles',
        title='Roles y permisos',
        model=Rol,
        form_class=RolForm,
        search_fields=(
            'nombre', 'descripcion', 'grupo__permissions__name', 'alcance',
        ),
        display_fields=(
            ('Nombre', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Permisos', 'permisos_resumen'),
            ('Alcance', 'alcance'),
            ('Estado', 'estado'),
            ('Protegido', 'protegido'),
        ),
        export_fields=(
            ('Nombre', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Permisos', 'permisos_resumen'),
            ('Alcance', 'alcance'),
            ('Estado', 'estado'),
            ('Protegido', 'protegido'),
        ),
        ordering=('nombre',),
        active_value=Rol.Estado.ACTIVO,
        inactive_value=Rol.Estado.INACTIVO,
    ),
    'items': MaintainerSpec(
        key='items',
        title='Ítems y metas',
        model=Item,
        form_class=ItemForm,
        search_fields=('codigo', 'nombre', 'descripcion', 'funcion__nombre'),
        display_fields=(
            ('Código', 'codigo'),
            ('Ítem', 'nombre'),
            ('Función', 'funcion__nombre'),
            ('Descripción', 'descripcion'),
            ('Metas asignadas', 'metas_asignadas'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Código', 'codigo'),
            ('Ítem', 'nombre'),
            ('Función', 'funcion__nombre'),
            ('Descripción', 'descripcion'),
            ('Metas asignadas', 'metas_asignadas'),
            ('Estado', 'estado'),
        ),
        ordering=('funcion__nombre', 'nombre'),
        active_value=Item.Estado.ACTIVO,
        inactive_value=Item.Estado.INACTIVO,
    ),
    'tipos-atencion': MaintainerSpec(
        key='tipos-atencion',
        title='Tipo de Atención',
        model=TipoAtencion,
        form_class=TipoAtencionForm,
        search_fields=('codigo', 'nombre', 'descripcion'),
        display_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        ordering=('nombre',),
        active_value=TipoAtencion.Estado.ACTIVO,
        inactive_value=TipoAtencion.Estado.INACTIVO,
    ),
    'subatenciones': MaintainerSpec(
        key='subatenciones',
        title='Sub Atención',
        model=SubAtencion,
        form_class=SubAtencionForm,
        search_fields=(
            'codigo', 'nombre', 'descripcion', 'tipo_atencion__nombre',
        ),
        display_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Tipo de Atención', 'tipo_atencion__nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        export_fields=(
            ('Código', 'codigo'),
            ('Nombre', 'nombre'),
            ('Tipo de Atención', 'tipo_atencion__nombre'),
            ('Descripción', 'descripcion'),
            ('Estado', 'estado'),
        ),
        ordering=('tipo_atencion__nombre', 'nombre'),
        active_value=SubAtencion.Estado.ACTIVO,
        inactive_value=SubAtencion.Estado.INACTIVO,
    ),
    'metas': MaintainerSpec(
        key='metas',
        title='Metas por usuario, ítem y período',
        model=Desempeno,
        form_class=DesempenoForm,
        search_fields=(
            'usuario__email', 'usuario__first_name', 'usuario__last_name',
            'item__codigo', 'item__nombre', 'periodo__nombre',
        ),
        display_fields=(
            ('Usuario', 'usuario'),
            ('Ítem', 'item'),
            ('Período', 'periodo'),
            ('Meta', 'meta'),
            ('Avance', 'avance'),
            ('Ponderación (%)', 'ponderacion'),
        ),
        export_fields=(
            ('Correo electrónico', 'usuario__email'),
            ('Usuario', 'usuario'),
            ('Código de ítem', 'item__codigo'),
            ('Ítem', 'item__nombre'),
            ('Período', 'periodo__nombre'),
            ('Meta', 'meta'),
            ('Avance', 'avance'),
            ('Ponderación (%)', 'ponderacion'),
        ),
        ordering=('periodo__nombre', 'usuario__email', 'item__nombre'),
        status_field=None,
        status_filter_field=None,
    ),
}


def excel_response(queryset, columns, filename):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Resultados'
    worksheet.append([label for label, _ in columns])
    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    for record in queryset.iterator(chunk_size=200):
        values = [display_value(record, field) for _, field in columns]
        worksheet.append([
            _safe_spreadsheet_value(value)
            for value in values
        ])

    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = worksheet.dimensions
    for column_cells in worksheet.columns:
        column_letter = column_cells[0].column_letter
        width = max(
            (len(str(cell.value or '')) for cell in column_cells),
            default=10,
        )
        worksheet.column_dimensions[column_letter].width = min(max(width + 2, 12), 60)

    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    return response


def _safe_spreadsheet_value(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        return value
    if value.lstrip(' \t\r\n')[:1] in {'=', '+', '-', '@'}:
        return f"'{value}"
    return value


def display_value(record, field_name):
    if field_name == 'roles':
        return ', '.join(sorted(role.nombre for role in record.roles.all()))
    if field_name == 'permisos_resumen':
        if not record.grupo_id:
            return 'Sin permisos'
        return ', '.join(
            record.grupo.permissions.order_by('codename').values_list(
                'name', flat=True,
            )
        ) or 'Sin permisos'
    if field_name == 'protegido':
        return 'Sí' if record.protegido else 'No'
    if field_name == 'delegaciones_autorizadas':
        return ', '.join(
            sorted(
                delegation.nombre
                for delegation in record.delegaciones_autorizadas.all()
            )
        )
    if field_name == 'is_active':
        return 'Activo' if record.is_active else 'Inactivo'
    if field_name == 'estado' or field_name == 'alcance':
        display_method = getattr(record, f'get_{field_name}_display', None)
        if display_method:
            return display_method()

    value = record
    for part in field_name.split('__'):
        value = getattr(value, part, None)
        if value is None:
            break
        if callable(value):
            value = value()
    return '' if value is None else str(value)


def _queryset_for(spec, request, *, global_scope=False):
    queryset = _authorized_queryset(
        spec, request, global_scope=global_scope,
    )
    query = request.GET.get('q', '').strip()
    if query:
        search = Q()
        for field in spec.search_fields:
            search |= Q(**{f'{field}__icontains': query})
        queryset = queryset.filter(search)

    status = request.GET.get('estado', '')
    if spec.status_filter_field:
        status_values = {
            str(spec.active_value): spec.active_value,
            str(spec.inactive_value): spec.inactive_value,
        }
        if status in status_values:
            queryset = queryset.filter(**{
                spec.status_filter_field: status_values[status],
            })

    return queryset.order_by(*spec.ordering)


def _authorized_queryset(spec, request, *, global_scope=False):
    if spec.key == 'items':
        return Item.objects.select_related('funcion').annotate(
            metas_asignadas=Count('desempenos'),
        )
    if spec.key == 'metas':
        queryset = Desempeno.objects.select_related(
            'usuario', 'item', 'periodo', 'funcion',
        )
        if (not global_scope and request.user.cargo
                and request.user.cargo.nombre.strip().casefold() not in {
            'admin', 'administrador',
        }):
            delegation = active_delegation(request)
            if delegation is None:
                return queryset.none()
            queryset = queryset.filter(
                Q(usuario__delegacion=delegation)
                | Q(usuario__delegaciones_autorizadas=delegation)
            ).distinct()
        return queryset
    if spec.key == 'subatenciones':
        return SubAtencion.objects.select_related('tipo_atencion')
    return spec.model.objects.all()


def _delete_block(spec, record, *, coordinator_meta_delete=False):
    if spec.key == 'cargos':
        return _cargo_delete_block(record)
    if spec.key == 'funciones':
        return _function_delete_block(record)
    if spec.key == 'catalogo':
        return _catalog_delete_block(record)
    if spec.key == 'delegaciones':
        return _delegation_delete_block(record)
    if spec.key == 'roles':
        return _role_delete_block(record)
    if spec.key == 'items':
        return _item_delete_block(record)
    if spec.key == 'tipos-atencion':
        return _type_delete_block(record)
    if spec.key == 'subatenciones':
        return _subtype_delete_block(record)
    if spec.key == 'metas':
        if coordinator_meta_delete:
            return _coordinator_meta_delete_block(record)
        return _meta_delete_block(record)
    return ''


def _snapshot(spec, record):
    return {
        field: display_value(record, field)
        for _, field in spec.export_fields
    }


def _form_kwargs(spec, request, *, global_scope=False, allow_closed_periods=False):
    if spec.key == 'roles':
        return {'actor': request.user}
    if spec.key == 'metas':
        return {
            'user': request.user,
            'delegation': active_delegation(request),
            'global_scope': global_scope,
            'allow_closed_periods': allow_closed_periods,
        }
    return {}


def _status_options(spec):
    if not spec.status_field:
        return ()
    field = spec.model._meta.get_field(spec.status_field)
    if spec.status_field == 'is_active':
        return (('activo', 'Activo'), ('inactivo', 'Inactivo'))
    return tuple(field.choices)


def _pagination_query(request):
    parameters = request.GET.copy()
    for key in ('page', 'export', 'editar', 'periodo'):
        parameters.pop(key, None)
    return parameters.urlencode()


def _maintainer_context(
    spec, request, form, editing, queryset, base_count, *,
    route_name=None, sgr_role=None, sidebar_modules=(),
    coordinator_meta_delete=False,
):
    page_obj = Paginator(queryset, 25).get_page(request.GET.get('page'))
    rows = [
        {
            'object': record,
            'values': [
                display_value(record, field)
                for _, field in spec.display_fields
            ],
            'can_delete': not bool(_delete_block(
                spec, record, coordinator_meta_delete=coordinator_meta_delete,
            )),
            'can_edit': not (
                spec.key == 'roles' and record.protegido
            ),
            'can_change_status': not (
                spec.key == 'roles' and record.protegido
            ),
            'can_duplicate': (
                spec.key == 'roles' and not record.protegido
            ),
        }
        for record in page_obj.object_list
    ]
    query = request.GET.get('q', '').strip()
    status = request.GET.get('estado', '')
    return {
        'sgr_role': 'Administración',
        'sgr_role': sgr_role or 'Administraci\u00f3n',
        'maintainer_title': spec.title,
        'form': form,
        'editing_object': editing,
        'rows': rows,
        'columns': [label for label, _ in spec.display_fields],
        'total_columns': len(spec.display_fields) + 1,
        'page_obj': page_obj,
        'pagination_query': _pagination_query(request),
        'query': query,
        'status': status,
        'status_options': _status_options(spec),
        'has_filters': bool(query or status),
        'base_count': base_count,
        'has_status': spec.status_field is not None,
        'is_item_maintainer': spec.key == 'items',
        'route_name': route_name or f'administracion:{spec.key}',
        'is_meta_maintainer': spec.key == 'metas',
        'is_role_maintainer': spec.key == 'roles',
        'sidebar_modules': sidebar_modules,
    }


def maintainer(
    request, key, *, route_name=None, sgr_role=None, sidebar_modules=(),
    protect_closed_periods=False, global_scope=False,
    coordinator_meta_delete=False, warn_weight_total=False,
    closed_period_authorization=False,
):
    spec = SPECS[key]
    status = request.GET.get('estado', '')
    valid_statuses = {
        '',
        str(spec.active_value),
        str(spec.inactive_value),
    } if spec.status_filter_field else {''}
    if status not in valid_statuses:
        return HttpResponseBadRequest('Filtro de estado no válido.')
    if request.GET.get('export', '') not in {'', 'excel'}:
        return HttpResponseBadRequest('Formato de exportación no válido.')
    authorized_queryset = _authorized_queryset(
        spec, request, global_scope=global_scope,
    )
    queryset = _queryset_for(
        spec, request, global_scope=global_scope,
    )
    base_count = authorized_queryset.count()
    editing = None
    form = None

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        object_id = request.POST.get('object_id')
        if action not in {'guardar', 'eliminar', 'cambiar_estado', 'duplicar'}:
            return HttpResponseBadRequest('Acción no válida.')
        if action == 'duplicar':
            if spec.key != 'roles':
                return HttpResponseBadRequest('La duplicación no está disponible.')
            source = get_object_or_404(authorized_queryset, pk=object_id)
            if source.protegido:
                messages.error(request, 'No se puede duplicar un rol protegido.')
                return redirect(request.path)
            source_permissions = (
                set(
                    source.grupo.permissions.values_list(
                        'codename',
                        flat=True,
                    )
                )
                if source.grupo_id else set()
            )
            if (
                not is_system_administrator(request.user)
                and not source_permissions.issubset(
                    permission_codenames_for(request.user)
                )
            ):
                messages.error(
                    request,
                    'No puedes duplicar un rol con permisos que tu cuenta no posee.',
                )
                return redirect(request.path)

            base_name = f'{source.nombre[:72]} (copia)'
            duplicate_name = base_name
            suffix = 2
            while Rol.objects.filter(nombre=duplicate_name).exists():
                duplicate_name = f'{source.nombre[:70]} (copia {suffix})'
                suffix += 1
            with transaction.atomic():
                duplicate = Rol.objects.create(
                    nombre=duplicate_name,
                    descripcion=source.descripcion,
                    alcance=source.alcance,
                    estado=Rol.Estado.ACTIVO,
                )
                duplicate_group = ensure_role_group(duplicate)
                duplicate_group.permissions.set(
                    source.grupo.permissions.all()
                    if source.grupo_id else []
                )
                registrar_historial(
                    actor=request.user,
                    action='Duplicar rol',
                    entity=f'Rol:{duplicate.pk}',
                    before=_snapshot(spec, source),
                    after=_snapshot(spec, duplicate),
                )
            messages.success(request, 'El rol se duplicó correctamente.')
            return redirect(f'{request.path}?editar={duplicate.pk}')
        if action in {'eliminar', 'cambiar_estado'}:
            if action == 'eliminar':
                try:
                    with transaction.atomic():
                        record = get_object_or_404(
                            authorized_queryset.select_for_update(),
                            pk=object_id,
                        )
                        authorization = (
                            authorization_for(request.user, record.periodo, funcionario=record.usuario)
                            if closed_period_authorization and record.periodo.estado == 'cerrado' else None
                        )
                        blocked = _delete_block(
                            spec, record,
                            coordinator_meta_delete=coordinator_meta_delete and not authorization,
                        )
                        if not blocked:
                            before = _snapshot(spec, record)
                            entity = f'{spec.model.__name__}:{record.pk}'
                            record.delete()
                            if authorization:
                                record_authorization_use(authorization, request.user)
                            registrar_historial(
                                actor=request.user,
                                action=f'Eliminar {spec.title.lower()}',
                                entity=entity,
                                before=before,
                            )
                    if blocked:
                        messages.error(request, blocked)
                    else:
                        messages.success(request, 'El registro se eliminó correctamente.')
                except ProtectedError:
                    messages.error(
                        request,
                        'No se puede eliminar porque existen registros asociados. '
                        'Desactiva el elemento para conservarlos.',
                    )
                return redirect(request.path)

            if not spec.status_field:
                return HttpResponseBadRequest('Este registro no tiene estado.')
            with transaction.atomic():
                record = get_object_or_404(
                    authorized_queryset.select_for_update(),
                    pk=object_id,
                )
                if spec.key == 'roles' and record.protegido:
                    messages.error(request, 'Este rol protegido no se puede modificar.')
                    return redirect(request.path)
                current_value = getattr(record, spec.status_field)
                new_value = (
                    spec.inactive_value
                    if current_value == spec.active_value
                    else spec.active_value
                )
                before = _snapshot(spec, record)
                setattr(record, spec.status_field, new_value)
                record.save(update_fields=[spec.status_field])
                registrar_historial(
                    actor=request.user,
                    action=f'Cambiar estado de {spec.title.lower()}',
                    entity=f'{spec.model.__name__}:{record.pk}',
                    before=before,
                    after=_snapshot(spec, record),
                )
            messages.success(request, 'El estado se actualizó correctamente.')
            return redirect(request.path)

        object_id = request.POST.get('object_id')
        editing = (
            get_object_or_404(authorized_queryset, pk=object_id)
            if object_id else None
        )
        if (
            protect_closed_periods and editing
            and editing.periodo.estado == 'cerrado'
            and not (closed_period_authorization and authorization_for(request.user, editing.periodo, funcionario=editing.usuario))
        ):
            messages.error(request, 'El per\u00edodo est\u00e1 cerrado; la meta es de solo lectura.')
            return redirect(request.path)
        before = _snapshot(spec, editing) if editing else None
        form = spec.form_class(
            request.POST,
            instance=editing,
            **_form_kwargs(spec, request, global_scope=global_scope, allow_closed_periods=closed_period_authorization),
        )
        if form.is_valid():
            authorization = None
            selected_period = form.cleaned_data.get('periodo') if spec.key == 'metas' else None
            selected_user = form.cleaned_data.get('usuario') if spec.key == 'metas' else None
            if closed_period_authorization and selected_period and selected_period.estado == 'cerrado':
                authorization = authorization_for(request.user, selected_period, funcionario=selected_user)
                if not authorization:
                    form.add_error(None, 'El perÃ­odo estÃ¡ cerrado y no existe una autorizaciÃ³n vigente para este funcionario.')
            if form.errors:
                messages.error(request, 'No existe una autorizaciÃ³n vigente para modificar esta meta.')
            else:
                with transaction.atomic():
                    record = form.save()
                    if authorization:
                        record_authorization_use(authorization, request.user)
                    registrar_historial(
                    actor=request.user,
                    action=(
                        f'Editar {spec.title.lower()}'
                        if editing else f'Crear {spec.title.lower()}'
                    ),
                    entity=f'{spec.model.__name__}:{record.pk}',
                    before=before,
                    after=_snapshot(spec, record),
                    )
                if warn_weight_total and spec.key == 'metas':
                    total = Desempeno.objects.filter(usuario_id=record.usuario_id, periodo_id=record.periodo_id).aggregate(total=Sum('ponderacion'))['total'] or 0
                    if total != 100:
                        relation = 'menor' if total < 100 else 'mayor'
                        messages.warning(request, f'Advertencia: la suma de ponderaciones de este funcionario en el perÃ­odo es {total:.2f}%, {relation} a 100%.')
                messages.success(request, 'Los cambios se guardaron correctamente.')
                return redirect(request.path)
        messages.error(request, 'Revisa los campos obligatorios y sus valores.')
    else:
        edit_id = request.GET.get('editar')
        editing = (
            get_object_or_404(authorized_queryset, pk=edit_id)
            if edit_id else None
        )
        if (
            protect_closed_periods and editing
            and editing.periodo.estado == 'cerrado'
            and not (closed_period_authorization and authorization_for(request.user, editing.periodo, funcionario=editing.usuario))
        ):
            messages.error(request, 'El per\u00edodo est\u00e1 cerrado; la meta es de solo lectura.')
            return redirect(request.path)
        form = spec.form_class(
            instance=editing,
            **_form_kwargs(spec, request, global_scope=global_scope, allow_closed_periods=closed_period_authorization),
        )

    context = _maintainer_context(
        spec,
        request,
        form,
        editing,
        queryset,
        base_count,
        route_name=route_name,
        sgr_role=sgr_role,
        sidebar_modules=sidebar_modules,
        coordinator_meta_delete=coordinator_meta_delete,
    )
    if request.GET.get('export') == 'excel':
        return excel_response(
            queryset,
            spec.export_fields,
            spec.key.replace('-', '_'),
        )
    return render(request, 'AdminApp/maintainer.html', context)
