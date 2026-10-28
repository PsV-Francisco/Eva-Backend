from config.delegations import active_delegation, authorized_delegations


NAVIGATION_BY_CARGO = {
    'admin': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Catálogo de actividades', 'administracion:catalogo'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Atenciones', None),
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
    ),
    'administrador': (
        ('Inicio', 'home'),
        ('Cargos', 'administracion:cargos'),
        ('Funciones', 'administracion:funciones'),
        ('Cargos por función', 'administracion:cargos-funciones'),
        ('Catálogo de actividades', 'administracion:catalogo'),
        ('Delegaciones', 'administracion:delegaciones'),
        ('Roles', 'administracion:roles'),
        ('Usuarios', 'administracion:home'),
        ('Ítems y metas', 'administracion:items'),
        ('Tipo de Atención', 'administracion:tipos-atencion'),
        ('Sub Atención', 'administracion:subatenciones'),
        ('Atenciones', None),
        ('Historial', 'administracion:historial'),
        ('Auditoría de recuperación', 'administracion:auditoria-recuperacion'),
    ),
    'funcionario': (
        ('Inicio', 'home'),
        ('Atenciones', 'funcionario:atencion_social'),
    ),
    'coordinador': (
        ('Inicio', 'home'),
        ('Ítems y metas', 'administracion:items'),
    ),
    'delegado': (
        ('Inicio', 'home'),
    ),
    'supervisor': (
        ('Inicio', 'home'),
    ),
    'verificador': (
        ('Inicio', 'home'),
    ),
    'vistaf': (
        ('Inicio', 'home'),
    ),
    'consulta': (
        ('Inicio', 'home'),
    ),
    'usuario de consulta': (
        ('Inicio', 'home'),
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
    navigation = NAVIGATION_BY_CARGO.get(role.strip().casefold(), ())
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
