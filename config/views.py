from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


@login_required
def home_redirect(request):
    cargo = request.user.cargo
    
    if not cargo:
        return redirect('login')
    
    nombre_cargo = cargo.nombre.lower()

    if nombre_cargo == 'funcionario':
        return redirect('funcionario:home')

    elif nombre_cargo == 'supervisor':
        return redirect('supervisor:home')
    
    elif nombre_cargo == 'delegado':
        return redirect('delegado:home')
    
    elif nombre_cargo == 'coordinador':
        return redirect('coordinador:home')

    elif nombre_cargo == 'administrador':
        return redirect('administracion:home')

    elif nombre_cargo == 'consulta':
        return redirect('vistaf:home')
    
    return redirect('login')

@require_GET
def health(request):
    return JsonResponse({'status': 'ok', 'service': 'sgr'})


@require_GET
def roles(request):
    return JsonResponse({
        'roles': [
            {'id': 'Funcionario', 'label': 'Funcionario'},
            {'id': 'Supervisor', 'label': 'Supervisor'},
            {'id': 'Delegado', 'label': 'Delegado'},
            {'id': 'Coordinador', 'label': 'Coordinador'},
            {'id': 'Admin', 'label': 'Administrador'},
            {'id': 'VistaF', 'label': 'Usuario de consulta'},
        ]
    })