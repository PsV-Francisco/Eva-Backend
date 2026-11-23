from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from config.permissions import PERMISSION_BY_CODENAME, can_access_permission


def cargo_required(*cargo_names, permission=None):
    if permission not in PERMISSION_BY_CODENAME:
        raise ValueError(
            'Cada vista protegida por cargo debe declarar un permiso del catálogo.'
        )
    accepted_cargos = {name.strip().casefold() for name in cargo_names}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if can_access_permission(
                request.user,
                permission,
                accepted_cargos,
            ):
                return view(request, *args, **kwargs)
            raise PermissionDenied

        wrapped.required_permission = permission
        wrapped.required_cargos = accepted_cargos
        return wrapped

    return decorator