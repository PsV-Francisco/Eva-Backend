from django.shortcuts import render

# Create your views here.
import json


def inicio(request):
    """Vista de la página de inicio"""
    with open('data/equipo.json', 'r', encoding='utf-8') as archivo:
        equipo = json.load(archivo)
    
    contexto = {
        'titulo': 'Página de Inicio',
        'equipo': equipo,
        'mensaje': 'Bienvenido a nuestro proyecto Django'
    }
    return render(request, 'app_inicio/inicio.html', contexto)

def about(request):
    """Vista de acerca de"""
    contexto = {
        'titulo': 'Acerca de',
        'descripcion': 'Este proyecto fue desarrollado como parte de la Evaluación Sumativa 1 de Programación Back End.'
    }
    return render(request, 'app_inicio/about.html', contexto)