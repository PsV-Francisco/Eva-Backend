import json
from pathlib import Path

from django.conf import settings
from django.shortcuts import render


def guia_ciudadana(request):
    data_path = Path(settings.BASE_DIR) / 'static' / 'data' / 'servicios_comunales.json'
    with data_path.open(encoding='utf-8') as archivo:
        servicios = json.load(archivo)

    return render(request, 'app_servicios/guia_ciudadana.html', {
        'titulo': 'Guia ciudadana',
        'servicios': servicios,
    })
