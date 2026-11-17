from django import template

from config.permissions import (
    PERMISSION_BY_VIEW,
    can_access_permission,
)


register = template.Library()

SIDEBAR_SECTIONS = (
    ('inicio', 'Inicio', '⌂'),
    ('organizacion', 'Organización', '▦'),
    ('territorio', 'Territorio', '⌖'),
    ('operacion', 'Operación', '✓'),
    ('metas-seguimiento', 'Metas y seguimiento', '◷'),
    ('informes', 'Informes', '▤'),
    ('auditoria', 'Auditoría', '▤'),
    ('consulta', 'Consulta', '⌕'),
    ('ayuda', 'Ayuda', '?'),
)

CURRENT_SECTION_BY_VIEW = {
    'coordinador:home': ('metas-seguimiento', 'Panel de Coordinación'),
    'coordinador:personal': ('metas-seguimiento', 'Tablero Personal'),
    'vistaf:home': ('consulta', 'Búsqueda de información'),
    'administracion:dashboard': ('inicio', 'Inicio'),
}


def _section_for(label, url_name):
    normalized_label = label.casefold()
    route = url_name or ''

    if route == 'manual' or 'manual' in normalized_label or 'ayuda' in normalized_label:
        return 'ayuda'
    if route in {'administracion:historial', 'administracion:auditoria-recuperacion'}:
        return 'auditoria'
    if route in {
        'coordinador:informes',
        'coordinador:tendencias',
        'administracion:informes',
        'administracion:informes-generados',
    } or 'informe' in normalized_label or 'reporte' in normalized_label:
        return 'informes'
    if route in {
        'administracion:vecinos',
        'administracion:juntas',
        'administracion:hitos',
        'funcionario:vecinos',
        'funcionario:vecino_nuevo',
        'funcionario:juntas',
    } or any(term in normalized_label for term in ('vecino', 'junta', 'hito')):
        return 'territorio'
    if (
        route == 'administracion:home'
        or 'roles' in normalized_label
        or 'usuarios' in normalized_label
        or any(term in normalized_label for term in ('cargo', 'funcion', 'delegacion'))
    ):
        return 'organizacion'
    if route in {
        'administracion:items',
        'administracion:metas',
        'administracion:parametros',
        'coordinador:home',
        'coordinador:personal',
        'coordinador:metas',
        'coordinador:ponderaciones',
        'administracion:resumen-delegacion',
        'funcionario:cumplimiento',
    } or any(term in normalized_label for term in ('meta', 'periodo', 'período', 'indicador', 'parámetro', 'item', 'ítem')):
        return 'metas-seguimiento'
    if route in {
        'funcionario:home',
        'funcionario:gestion_actividades',
        'funcionario:atencion_social',
        'funcionario:agenda_colectiva',
        'supervisor:home',
        'delegado:home',
        'delegado:resumen',
        'administracion:tipos-atencion',
        'administracion:subatenciones',
        'administracion:ausencias',
        'administracion:felicitaciones',
        'administracion:reclamos',
        'administracion:registros',
        'administracion:atenciones-sociales',
        'administracion:compromisos',
    } or any(term in normalized_label for term in ('atencion', 'atención', 'subatencion', 'subatención', 'catalogo', 'catálogo', 'actividad', 'compromiso', 'agenda', 'validar')):
        return 'operacion'
    if route == 'vistaf:home' or any(term in normalized_label for term in ('busqueda', 'búsqueda', 'consulta', 'informacion', 'información')):
        return 'consulta'
    if route == 'home' or normalized_label == 'inicio':
        return 'inicio'
    return 'operacion'


def _item_icon(url_name, label):
    if url_name == 'home' or label.casefold() == 'inicio':
        return '⌂'
    if 'rol' in label.casefold() or 'usuario' in label.casefold():
        return '♙'
    if 'cargo' in label.casefold() or 'funcion' in label.casefold():
        return '▦'
    if 'delegacion' in label.casefold():
        return '⌖'
    if 'meta' in label.casefold() or 'item' in label.casefold() or 'ítem' in label.casefold():
        return '◷'
    if 'atencion' in label.casefold() or 'atención' in label.casefold():
        return '◉'
    if 'evidencia' in label.casefold() or 'validar' in label.casefold():
        return '✓'
    if 'compromiso' in label.casefold() or 'agenda' in label.casefold():
        return '▣'
    if 'historial' in label.casefold() or 'auditoría' in label.casefold():
        return '▤'
    if 'manual' in label.casefold() or 'ayuda' in label.casefold():
        return '?'
    return '•'


@register.simple_tag
def sidebar_sections(primary_navigation, primary_navigation_urls, sidebar_modules, current_view, user):
    section_items = {key: [] for key, _, _ in SIDEBAR_SECTIONS}
    seen_urls = set(primary_navigation_urls or ())

    def add_item(label, url_name, is_primary=False):
        label = str(label).strip()
        if not label:
            return
        if url_name and url_name in seen_urls and not is_primary:
            return
        definition = PERMISSION_BY_VIEW.get(url_name)
        if definition and not can_access_permission(
            user,
            definition.codename,
            definition.cargos,
        ):
            return
        is_current = url_name == current_view or (
            url_name == 'administracion:items'
            and current_view == 'administracion:metas'
        )
        item = {
            'label': label,
            'url_name': url_name,
            'icon': _item_icon(url_name, label),
            'is_current': is_current,
        }
        section_items[_section_for(label, url_name)].append(item)
        if url_name:
            seen_urls.add(url_name)

    for item in primary_navigation or ():
        add_item(item.get('label', ''), item.get('url_name'), is_primary=True)
    for item in sidebar_modules or ():
        if isinstance(item, dict):
            add_item(item.get('label', ''), item.get('url_name'))
        else:
            add_item(item, None)

    current_section = CURRENT_SECTION_BY_VIEW.get(current_view)
    if current_section:
        section_key, current_label = current_section
        matching_item = next(
            (
                item for item in section_items[section_key]
                if item['label'].casefold() == current_label.casefold()
            ),
            None,
        )
        if matching_item:
            matching_item['is_current'] = True

    sections = []
    for key, label, icon in SIDEBAR_SECTIONS:
        items = section_items[key]
        if items:
            sections.append({
                'key': key,
                'label': label,
                'icon': icon,
                'items': items,
                'is_current': any(item['is_current'] for item in items),
            })
    return sections
