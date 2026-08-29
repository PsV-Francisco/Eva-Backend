from django.shortcuts import render

# Create your views here.
import json


def lista_noticias(request):
    """Vista que muestra todas las noticias"""
    with open('static/data/noticias.json', 'r', encoding='utf-8') as archivo:
        noticias = json.load(archivo)
    
    contexto = {
        'titulo': 'Noticias de La Serena',
        'noticias': noticias
    }
    return render(request, 'app_noticias/lista_noticias.html', contexto)

def detalle_noticia(request, id_noticia):
    """Vista que muestra el detalle de una noticia específica"""
    with open('static/data/noticias.json', 'r', encoding='utf-8') as archivo:
        noticias = json.load(archivo)
    
    noticia = None
    for n in noticias:
        if n['id'] == int(id_noticia):
            noticia = n
            break
    
    contexto = {
        'titulo': 'Detalle de Noticia',
        'noticia': noticia
    }
    return render(request, 'app_noticias/detalle_noticia.html', contexto)