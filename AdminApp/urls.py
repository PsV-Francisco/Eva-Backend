from django.urls import path

from . import admin_records
from . import views

app_name = 'administracion'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('usuarios/', views.home, name='home'),
    path('cargos/', views.cargos, name='cargos'),
    path('funciones/', views.funciones, name='funciones'),
    path('cargos-funciones/', views.cargos_funciones, name='cargos-funciones'),
    path('roles/', views.roles, name='roles'),
    path('tipos-atencion/', views.tipos_atencion, name='tipos-atencion'),
    path('subatenciones/', views.subatenciones, name='subatenciones'),
    path('parametros/', views.parametros, name='parametros'),
    path('historial/', views.historial, name='historial'),
    path('solicitudes-autorizacion/', views.solicitudes_autorizacion, name='solicitudes-autorizacion'),
    path('auditoria-recuperacion/',views.password_reset_audit,name='auditoria-recuperacion',),
    path('ajustes-metas/', admin_records.ajustes_metas, name='ajustes-metas'),
    path('informes-generados/', admin_records.informes_generados, name='informes-generados'),
    path('resumen-delegacion/', admin_records.resumen_delegacion, name='resumen-delegacion'),

    #Delegaciones
    path('delegaciones/', views.delegaciones, name='delegaciones'),
    path('delegaciones/buscar-ajax/', views.buscar_delegaciones_ajax, name='buscar_delegaciones_ajax'),
    path('delegaciones/<int:delegacion_id>/detalle-json/', views.detalle_delegacion_json, name='detalle_delegacion_json'),
    path('delegaciones/<int:delegacion_id>/editar-ajax/', views.editar_delegacion_ajax, name='editar_delegacion_ajax'),
    path('delegaciones/<int:delegacion_id>/cambiar-estado-ajax/', views.cambiar_estado_delegacion_ajax, name='cambiar_estado_delegacion_ajax'),
    #Items
    path('items/', views.items, name='items'),
    path('items/metas/', views.metas, name='metas'),
    path('items/buscar-ajax/', views.buscar_items_ajax, name='buscar_items_ajax'),
    path('items/<int:item_id>/detalle-json/', views.detalle_item_json, name='detalle_item_json'),
    path('items/<int:item_id>/editar-ajax/', views.editar_item_ajax, name='editar_item_ajax'),
    #Gestión de Ausencias
    path('ausencias/', admin_records.ausencias, name='ausencias'),
    path('ausencias/nueva/', admin_records.ausencia_nueva, name='ausencia-nueva'),
    path('ausencias/<int:ausencia_id>/editar/', admin_records.ausencia_editar,name='ausencia-editar',),
    path('ausencias/<int:ausencia_id>/eliminar/',admin_records.ausencia_eliminar,name='ausencia-eliminar',),
    #Gestión de Felicitaciones
    path('felicitaciones/', admin_records.felicitaciones, name='felicitaciones'),
    path('felicitaciones/nueva/', admin_records.felicitacion_nueva, name='felicitacion-nueva'),
    path('felicitaciones/<int:record_id>/editar/',admin_records.felicitacion_editar,name='felicitacion-editar',),
    path('felicitaciones/<int:record_id>/eliminar/',admin_records.felicitacion_eliminar,name='felicitacion-eliminar',),
    #Gestión de Reclamos
    path('reclamos/', admin_records.reclamos, name='reclamos'),
    path('reclamos/nuevo/', admin_records.reclamo_nuevo, name='reclamo-nuevo'),
    path('reclamos/<int:record_id>/editar/',admin_records.reclamo_editar,name='reclamo-editar',),
    path('reclamos/<int:record_id>/eliminar/',admin_records.reclamo_eliminar,name='reclamo-eliminar',),
    #Gestión de Hitos
    path('hitos/', admin_records.hitos, name='hitos'),
    path('hitos/nuevo/', admin_records.hito_nuevo, name='hito-nuevo'),
    path('hitos/<int:record_id>/editar/',admin_records.hito_editar,name='hito-editar',),
    path('hitos/<int:record_id>/eliminar/',admin_records.hito_eliminar,name='hito-eliminar',),
    #Gestion de Vecinos
    path('vecinos/', admin_records.vecinos, name='vecinos'),
    path('vecinos/nuevo/', admin_records.vecino_nuevo, name='vecino-nuevo'),
    path('vecinos/<int:vecino_id>/editar/',admin_records.vecino_editar,name='vecino-editar',),
    path('vecinos/<int:vecino_id>/eliminar/',admin_records.vecino_eliminar,name='vecino-eliminar',),
    #Getión de Registros
    path('registros/', admin_records.registros, name='registros'),
    path('registros/nuevo/', admin_records.registro_nuevo, name='registro-nuevo'),
    path('registros/<int:record_id>/editar/',admin_records.registro_editar,name='registro-editar',),
    #Gestión de Atenciones Sociales
    path('atenciones-sociales/', admin_records.atenciones_sociales, name='atenciones-sociales'),
    path('atenciones-sociales/nueva/',admin_records.atencion_social_nueva,name='atencion-social-nueva',),
    path('atenciones-sociales/<int:record_id>/editar/',admin_records.atencion_social_editar,name='atencion-social-editar',),
    #Gestión de Compromisos
    path('compromisos/', admin_records.compromisos, name='compromisos'),
    path('compromisos/nuevo/', admin_records.compromiso_nuevo, name='compromiso-nuevo'),
    path('compromisos/<int:record_id>/editar/',admin_records.compromiso_editar,name='compromiso-editar',),
    #Gestión de Juntas de Vecinos
    path('juntas/', admin_records.juntas, name='juntas'),
    path('juntas/nueva/', admin_records.junta_nueva, name='junta-nueva'),
    path('juntas/<int:junta_id>/editar/',admin_records.junta_editar,name='junta-editar',),
    path('juntas/<int:junta_id>/eliminar/',admin_records.junta_eliminar,name='junta-eliminar',),
    #Gestión de Beneficiados (Se debe borrar porque ya existen los vecinos)
    path('beneficiados/', views.beneficiados_vista, name='beneficiados'),
    path('beneficiados/crear-ajax/', views.crear_beneficiado_ajax, name='crear_beneficiado_ajax'),
    path('beneficiados/<int:beneficiado_id>/detalle-json/', views.detalle_beneficiado_json, name='detalle_beneficiado_json'),
    path('beneficiados/<int:beneficiado_id>/editar-ajax/', views.editar_beneficiado_ajax, name='editar_beneficiado_ajax'),
    path('beneficiados/<int:beneficiado_id>/eliminar/', views.eliminar_beneficiado, name='eliminar_beneficiado'),
]
