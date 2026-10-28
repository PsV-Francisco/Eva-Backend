from config.delegations import active_delegation, authorized_delegations
from config.permissions import (
    PERMISSION_BY_VIEW,
    PERMISSION_CATALOG,
    can_access_permission,
    permission_name,
)


NAVIGATION_BY_CARGO = {
    'admin': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Catálogo de actividades', 'administracion:catalogo'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles y permisos', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Atenciones', None),
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
        ('Manual / Ayuda', 'manual'),
    ),
    'administrador': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Catálogo de actividades', 'administracion:catalogo'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles y permisos', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Atenciones', None),
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
            'active_delegation_code': '',
            'header_role': '',
            'primary_navigation': (),
            'primary_navigation_urls': (),
        }

    delegation = active_delegation(request)
    delegations = tuple(authorized_delegations(request.user))
    cargo = request.user.cargo
    role = cargo.nombre if cargo else 'Usuario'
    navigation = list(NAVIGATION_BY_CARGO.get(role.strip().casefold(), ()))
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
        'active_delegation_code': delegation.codigo if delegation else '',
        'header_role': role,
        'primary_navigation': tuple(
            {'label': label, 'url_name': url_name}
            for label, url_name in navigation
        ),
        'primary_navigation_urls': tuple(
            url_name for _, url_name in navigation if url_name
        ),
    }
