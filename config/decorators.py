from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def cargo_required(*cargo_names):
    accepted_cargos = {name.strip().casefold() for name in cargo_names}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            cargo = request.user.cargo
            if cargo and cargo.nombre.strip().casefold() in accepted_cargos:
                return view(request, *args, **kwargs)
            raise PermissionDenied

        return wrapped

    return decorator