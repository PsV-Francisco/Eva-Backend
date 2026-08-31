from django.urls import path

from . import views


urlpatterns = [
    path('', views.lista_noticias, name='lista_noticias'),
    path('noticia/<int:id_noticia>/', views.detalle_noticia, name='detalle_noticia'),
]