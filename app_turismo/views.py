from django.shortcuts import render
import json


def get_turismo_data():
    with open('static/data/turismo.json', 'r', encoding='utf-8') as archivo:
        return json.load(archivo)


def turismo(request):
    zonas = get_turismo_data()
    contexto = {
        'titulo': 'Turismo regional',
        'zonas': zonas,
        'mensaje': 'Descubre rutas, miradores y experiencias del norte de Chile.'
    }
    return render(request, 'app_turismo/turismo.html', contexto)
