from config.delegations import active_delegation, authorized_delegations
from config.permissions import (
    PERMISSION_BY_VIEW,
    PERMISSION_CATALOG,
    can_access_permission,
    cargo_key_for_access,
    permission_name,
)


NAVIGATION_BY_CARGO = {
    'admin': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles y permisos', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Metas', 'administracion:metas'),
        ('Ajustes de Metas', 'administracion:ajustes-metas'),
        ('Ponderaciones', 'coordinador:ponderaciones'),
        ('Informes de Coordinación', 'coordinador:informes'),
        ('Informes Generados', 'administracion:informes-generados'),
        ('Resumen de Delegación', 'administracion:resumen-delegacion'),
        ('Tendencias históricas', 'coordinador:tendencias'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Ausencias', 'administracion:ausencias'),
        ('Felicitaciones', 'administracion:felicitaciones'),
        ('Reclamos', 'administracion:reclamos'),
        ('Hitos', 'administracion:hitos'),
        ('Registros', 'administracion:registros'),
        ('Atenciones Sociales', 'administracion:atenciones-sociales'),
        ('Compromisos', 'administracion:compromisos'),
        ('Vecinos', 'administracion:vecinos'),
        ('Juntas de Vecinos', 'administracion:juntas'),
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
        ('Manual / Ayuda', 'manual'),
    ),
    'administrador': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles y permisos', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Metas', 'administracion:metas'),
        ('Ajustes de Metas', 'administracion:ajustes-metas'),
        ('Ponderaciones', 'coordinador:ponderaciones'),
        ('Informes de Coordinación', 'coordinador:informes'),
        ('Informes Generados', 'administracion:informes-generados'),
        ('Resumen de Delegación', 'administracion:resumen-delegacion'),
        ('Tendencias históricas', 'coordinador:tendencias'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Ausencias', 'administracion:ausencias'),
        ('Felicitaciones', 'administracion:felicitaciones'),
        ('Reclamos', 'administracion:reclamos'),
        ('Hitos', 'administracion:hitos'),
        ('Registros', 'administracion:registros'),
        ('Atenciones Sociales', 'administracion:atenciones-sociales'),
        ('Compromisos', 'administracion:compromisos'),
        ('Vecinos', 'administracion:vecinos'),
        ('Juntas de Vecinos', 'administracion:juntas'),
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
        ('Manual / Ayuda', 'manual'),
    ),
    'funcionario': (
        ('Inicio', 'home'),
        ('Atenciones', 'funcionario:atencion_social'),
        ('Manual / Ayuda', 'manual'),
    ),
    'coordinador': (
        ('Inicio', 'home'),
        ('Ítems y metas', 'administracion:items'),
        ('Manual / Ayuda', 'manual'),
    ),
    'delegado': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
    'supervisor': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
    'verificador': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
    'vistaf': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
    'consulta': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
    'usuario de consulta': (
        ('Inicio', 'home'),
        ('Manual / Ayuda', 'manual'),
    ),
}


def common_header(request):
    if not request.user.is_authenticated:
        return {
            'active_delegation': None,
            'authorized_delegations': (),
            'header_role': '',
            'primary_navigation': (),
            'primary_navigation_urls': (),
        }

    delegation = active_delegation(request)
    delegations = tuple(authorized_delegations(request.user))
    cargo = getattr(request.user, 'cargo', None)
    role = cargo.nombre if cargo else ''
    if not role:
        roles = getattr(request.user, 'roles', None)
        if roles is not None:
            role_list = roles.all() if hasattr(roles, 'all') else roles
            first_role = next(iter(role_list), None)
            if first_role:
                role = getattr(first_role, 'nombre', '')

    role_key = cargo_key_for_access(role) or role.strip().casefold()
    navigation = list(NAVIGATION_BY_CARGO.get(role_key, ()))
    for definition in PERMISSION_CATALOG:
        if (
            definition.show_in_menu
            and request.user.has_perm(permission_name(definition.codename))
            and all(url_name != definition.view_name for _, url_name in navigation)
        ):
            navigation.append((definition.label, definition.view_name))
    navigation = tuple(
        (label, url_name)
        for label, url_name in navigation
        if (
            url_name not in PERMISSION_BY_VIEW
            or can_access_permission(
                request.user,
                PERMISSION_BY_VIEW[url_name].codename,
                PERMISSION_BY_VIEW[url_name].cargos,
            )
        )
    )
    return {
        'active_delegation': delegation,
        'authorized_delegations': delegations,
        'header_role': role,
        'primary_navigation': tuple(
            {'label': label, 'url_name': url_name}
            for label, url_name in navigation
        ),
        'primary_navigation_urls': tuple(
            url_name for _, url_name in navigation if url_name
        ),
    }
