from django.urls import path

from . import views

app_name = 'funcionario'

urlpatterns = [
    path('', views.home, name='home'),
    path('actividades/', views.gestion_actividades, name='gestion_actividades'),
    path('vecinos/', views.vecinos, name='vecinos'),
    path('vecinos/nuevo/', views.vecino_form, name='vecino_nuevo'),
    path('vecinos/<int:vecino_id>/editar/', views.editar_vecino, name='vecino_editar'),
    path('vecinos/<int:vecino_id>/desactivar/', views.desactivar_vecino, name='vecino_desactivar'),
    path('vecinos/<int:vecino_id>/eliminar/', views.eliminar_vecino, name='vecino_eliminar'),
    path('juntas/', views.juntas, name='juntas'),
    path('juntas/nueva/', views.junta_form, name='junta_nueva'),
    path('juntas/<int:junta_id>/editar/', views.editar_junta, name='junta_editar'),
    path('juntas/<int:junta_id>/desactivar/', views.desactivar_junta, name='junta_desactivar'),
    path('juntas/<int:junta_id>/eliminar/', views.eliminar_junta, name='junta_eliminar'),
    path('cumplimiento/', views.cumplimiento, name='cumplimiento'),
    path('atencion-social/', views.atencion_social, name='atencion_social'),
    path('atencion-social/solicitantes/', views.buscar_solicitantes, name='buscar_solicitantes'),
    path(
        'atencion-social/tipos/<int:tipo_id>/subatenciones/',
        views.subatenciones_tipo,
        name='subatenciones_tipo',
    ),
    path('agenda-colectiva/', views.agenda_colectiva, name='agenda_colectiva'),
    path('compromisos/nuevo/', views.nuevo_compromiso, name='compromiso_nuevo'),
    path('compromisos/<int:compromiso_id>/editar/', views.editar_compromiso, name='compromiso_editar'),
    path('compromisos/<int:compromiso_id>/evidencia/', views.cargar_evidencia_compromiso, name='compromiso_evidencia'),
]
