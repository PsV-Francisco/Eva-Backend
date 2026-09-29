import json
from pathlib import Path
from django.conf import settings
from django.shortcuts import render


def guia_ciudadana(request):
    """Vista que muestra la página de la guia ciudadana"""
    #Búsqueda del archivo JSON
    data_path = Path(settings.BASE_DIR) / 'static' / 'data' / 'servicios_comunales.json'
    with data_path.open(encoding='utf-8') as archivo:
        servicios = json.load(archivo)

    #Retorno de la página con la info
    return render(request, 'app_servicios/guia_ciudadana.html', {
        'titulo': 'Guia ciudadana',
        'servicios': servicios,
    })


def lugares_servicios(request):
    """Muestra los lugares de servicios publicos desde un archivo JSON."""
    data_path = Path(settings.BASE_DIR) / 'static' / 'data' / 'lugares_servicios.json'
    with data_path.open(encoding='utf-8') as archivo:
        lugares = json.load(archivo)

    return render(request, 'app_servicios/lugares_servicios.html', {
        'titulo': 'Lugares de servicios publicos',
        'lugares': lugares,
    })
