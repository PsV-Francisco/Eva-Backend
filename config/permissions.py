from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDefinition:
    module: str
    codename: str
    label: str
    view_name: str
    cargos: tuple[str, ...]
    route_kwargs: tuple[tuple[str, object], ...] = ()
    show_in_menu: bool = True


PERMISSION_CATALOG = (
    PermissionDefinition('Administración', 'access_admin_users', 'Administrar usuarios', 'administracion:home', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_parameters', 'Administrar parámetros del sistema', 'administracion:parametros', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_delegations', 'Administrar delegaciones', 'administracion:delegaciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_positions', 'Administrar cargos', 'administracion:cargos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_functions', 'Administrar funciones', 'administracion:funciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_position_functions', 'Administrar cargos por función', 'administracion:cargos-funciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_catalog', 'Administrar catálogo de actividades', 'administracion:catalogo', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_roles', 'Administrar roles y permisos', 'administracion:roles', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_items', 'Administrar ítems', 'administracion:items', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_attention_types', 'Administrar tipos de atención', 'administracion:tipos-atencion', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_subattentions', 'Administrar subatenciones', 'administracion:subatenciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_goals', 'Administrar metas', 'administracion:metas', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_history', 'Consultar historial', 'administracion:historial', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_password_audit', 'Consultar auditoría de recuperación', 'administracion:auditoria-recuperacion', ('admin', 'administrador')),
    PermissionDefinition('Funcionario', 'access_employee_dashboard', 'Consultar registro de actividades', 'funcionario:home', ('funcionario',)),
    PermissionDefinition('Funcionario', 'manage_employee_compliance', 'Consultar cumplimiento', 'funcionario:cumplimiento', ('funcionario',)),
    PermissionDefinition('Funcionario', 'manage_social_care', 'Administrar atención social', 'funcionario:atencion_social', ('funcionario',)),
    PermissionDefinition('Funcionario', 'search_social_applicants', 'Buscar solicitantes', 'funcionario:buscar_solicitantes', ('funcionario',)),
    PermissionDefinition(
        'Funcionario',
        'view_social_subattentions',
        'Consultar subatenciones por tipo',
        'funcionario:subatenciones_tipo',
        ('funcionario',),
        (('tipo_id', 1),),
        False,
    ),
    PermissionDefinition('Funcionario', 'manage_collective_agenda', 'Administrar agenda colectiva', 'funcionario:agenda_colectiva', ('funcionario',)),
    PermissionDefinition('Supervisor / Verificador', 'review_evidence', 'Revisar y validar evidencias', 'supervisor:home', ('supervisor', 'verificador')),
    PermissionDefinition('Delegado', 'manage_commitments', 'Administrar compromisos', 'delegado:home', ('delegado',)),
    PermissionDefinition('Delegado', 'view_delegation_summary', 'Consultar resumen de delegación', 'delegado:resumen', ('delegado',)),
    PermissionDefinition('Coordinador', 'manage_periods', 'Administrar períodos e indicadores', 'coordinador:home', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Consulta', 'view_public_reports', 'Consultar información', 'vistaf:home', ('vistaf', 'consulta', 'usuario de consulta')),
)

PERMISSION_BY_CODENAME = {
    definition.codename: definition
    for definition in PERMISSION_CATALOG
}
PERMISSION_BY_VIEW = {
    definition.view_name: definition
    for definition in PERMISSION_CATALOG
}


def permission_name(codename):
    return f'AdminApp.{codename}'


def has_cargo_access(user, cargos):
    cargo = getattr(user, 'cargo', None)
    if cargo and cargo.nombre.strip().casefold() in {
        name.strip().casefold() for name in cargos
    }:
        return True
    return bool(
        cargo
        and cargo.nombre.strip().casefold() in {'admin', 'administrador'}
    )


def can_access_permission(user, codename, cargos=()):
    if getattr(user, 'is_superuser', False) and not has_cargo_access(
        user,
        cargos,
    ):
        return False
    return (
        has_cargo_access(user, cargos)
        or user.has_perm(permission_name(codename))
    )
