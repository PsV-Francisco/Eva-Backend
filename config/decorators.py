from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*role_names, allow_staff=False):
    accepted_roles = {name.casefold() for name in role_names}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or (allow_staff and user.is_staff):
                return view(request, *args, **kwargs)
            assigned_roles = {
                name.casefold() for name in user.roles.values_list('nombre', flat=True)
            }
            if accepted_roles.intersection(assigned_roles):
                return view(request, *args, **kwargs)
            raise PermissionDenied

        return wrapped

    return decorator