from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


@login_required
def home_redirect(request):
    cargo = request.user.cargo
    if not cargo:
        raise PermissionDenied

    cargo_routes = {
        'funcionario': 'funcionario:home',
        'supervisor': 'supervisor:home',
        'verificador': 'supervisor:home',
        'delegado': 'delegado:home',
        'coordinador': 'coordinador:home',
        'admin': 'administracion:home',
        'administrador': 'administracion:home',
        'vistaf': 'vistaf:home',
        'consulta': 'vistaf:home',
        'usuario de consulta': 'vistaf:home',
    }
    route_name = cargo_routes.get(cargo.nombre.strip().casefold())
    if route_name is None:
        raise PermissionDenied
    return redirect(route_name)