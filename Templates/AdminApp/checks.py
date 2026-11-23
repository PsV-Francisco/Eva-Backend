from django.core.checks import Error, register
from django.urls import (
    NoReverseMatch,
    URLPattern,
    URLResolver,
    get_resolver,
    resolve,
    reverse,
)

from config.permissions import PERMISSION_BY_VIEW


def _named_view_callbacks(patterns, namespace=''):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            child_namespace = ':'.join(
                item for item in (namespace, pattern.namespace) if item
            )
            yield from _named_view_callbacks(
                pattern.url_patterns,
                child_namespace,
            )
        elif isinstance(pattern, URLPattern):
            if pattern.name and namespace:
                view_name = f'{namespace}:{pattern.name}'
            else:
                view_name = pattern.name or ''
            yield view_name, pattern.callback


@register()
def permission_catalog_check(app_configs, **kwargs):
    errors = []
    seen_codenames = set()
    for view_name, definition in PERMISSION_BY_VIEW.items():
        if definition.codename in seen_codenames:
            errors.append(Error(
                f'El permiso {definition.codename} está asignado a más de una vista.',
                id='roles.E003',
            ))
        seen_codenames.add(definition.codename)
        try:
            callback = resolve(reverse(
                view_name,
                kwargs=dict(definition.route_kwargs),
            )).func
        except NoReverseMatch:
            errors.append(Error(
                f'La vista protegida {view_name} no tiene una ruta resoluble.',
                id='roles.E001',
            ))
            continue

        if getattr(callback, 'required_permission', None) != definition.codename:
            errors.append(Error(
                f'La vista {view_name} no está protegida con '
                f'{definition.codename}.',
                id='roles.E002',
            ))

    for view_name, callback in _named_view_callbacks(
        get_resolver().url_patterns,
    ):
        codename = getattr(callback, 'required_permission', None)
        if codename and (
            view_name not in PERMISSION_BY_VIEW
            or PERMISSION_BY_VIEW[view_name].codename != codename
        ):
            errors.append(Error(
                f'La vista protegida {view_name or callback.__name__} no tiene '
                'una asociación propia en el catálogo de permisos.',
                id='roles.E004',
            ))
    return errors
