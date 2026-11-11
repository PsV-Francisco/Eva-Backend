from django.urls import path
from . import views
app_name = 'funcionario'
urlpatterns = [
    path('', views.home, name='home'),
    path('actividades/', views.gestion_actividades, name='gestion_actividades'),
    path('actividades/<int:registro_id>/detalle-json/', views.detalle_registro_json, name='detalle_registro_json'),
    path('actividades/<int:registro_id>/editar-ajax/', views.editar_registro_ajax, name='editar_registro_ajax'),
    path('actividades/subtipos-por-tipo/<int:tipo_id>/', views.subtipos_por_tipo, name='subtipos_por_tipo'),
    path('cumplimiento/', views.cumplimiento, name='cumplimiento'),
    #URLS De Vecinos
    path('vecinos/', views.vecinos, name='vecinos'),
    path('vecinos/<int:vecino_id>/detalle-json/', views.detalle_vecino_json, name='detalle_vecino_json'),
    path('vecinos/<int:vecino_id>/editar-ajax/', views.editar_vecino_ajax, name='editar_vecino_ajax'),
    path('vecinos/<int:vecino_id>/desactivar/', views.desactivar_vecino, name='vecino_desactivar'),
    path('vecinos/<int:vecino_id>/eliminar/', views.eliminar_vecino, name='vecino_eliminar'),
    path('vecinos/nuevo/', views.vecino_form, name='vecino_form'),
    path('vecinos/<int:vecino_id>/editar/', views.editar_vecino, name='editar_vecino'),
    # URLS de Junta de Vecinos
    path('juntas/', views.juntas, name='juntas'),
    path('juntas/<int:junta_id>/detalle-json/', views.detalle_junta_json, name='detalle_junta_json'),
    path('juntas/<int:junta_id>/editar-ajax/', views.editar_junta_ajax, name='editar_junta_ajax'),
    path('juntas/<int:junta_id>/desactivar/', views.junta_desactivar, name='junta_desactivar'),
    path('juntas/<int:junta_id>/eliminar/', views.eliminar_junta, name='junta_eliminar'),
    path('juntas/nueva/', views.junta_form, name='junta_form'),
    path('juntas/<int:junta_id>/editar/', views.editar_junta, name='editar_junta'),
    path('territorios-por-delegacion/<int:delegacion_id>/', views.territorios_por_delegacion, name='territorios_por_delegacion'),
    # URLS de Atención Social
    path('atencion-social/', views.atencion_social, name='atencion_social'),
    path('atencion-social/<int:atencion_id>/detalle-json/', views.detalle_atencion_json, name='detalle_atencion_json'),
    path('atencion-social/<int:atencion_id>/editar-ajax/', views.editar_atencion_ajax, name='editar_atencion_ajax'),
    path('atencion-social/solicitantes/', views.buscar_solicitantes, name='buscar_solicitantes'),
    path('atencion-social/tipos/<int:tipo_id>/subatenciones/', views.subatenciones_tipo, name='subatenciones_tipo'),
    # URLS de Gestión de Casos / Gestiones Sociales
    path('casos-sociales/', views.casos_sociales, name='casos_sociales'),
    path('casos-sociales/crear-ajax/', views.crear_gestion_social_ajax, name='crear_gestion_social_ajax'),
    path('casos-sociales/<int:gestion_id>/detalle-json/', views.detalle_gestion_social_json, name='detalle_gestion_social_json'),
    path('casos-sociales/<int:gestion_id>/editar-ajax/', views.editar_gestion_social_ajax, name='editar_gestion_social_ajax'),
    #URLS de Agenda Colectiva
    path('agenda-colectiva/', views.agenda_colectiva, name='agenda_colectiva'),
    path('compromisos/nuevo/', views.nuevo_compromiso, name='compromiso_nuevo'),
    path('compromisos/<int:compromiso_id>/editar/',views.editar_compromiso,name='compromiso_editar',),
    path('compromisos/<int:compromiso_id>/evidencia/',views.cargar_evidencia_compromiso,name='compromiso_evidencia',),
]