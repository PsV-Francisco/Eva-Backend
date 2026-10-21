from django.urls import path

from . import views

app_name = 'funcionario'

urlpatterns = [
    path('', views.home, name='home'),
    path('cumplimiento/', views.cumplimiento, name='cumplimiento'),
    path('atencion-social/', views.atencion_social, name='atencion_social'),
    path('atencion-social/solicitantes/', views.buscar_solicitantes, name='buscar_solicitantes'),
    path(
        'atencion-social/tipos/<int:tipo_id>/subatenciones/',
        views.subatenciones_tipo,
        name='subatenciones_tipo',
    ),
    path('agenda-colectiva/', views.agenda_colectiva, name='agenda_colectiva'),
]