from django.http import JsonResponse
from django.views.decorators.http import require_GET


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
            {'id': 'VistaF', 'label': 'Vista pendiente de definición'},
        ]
    })