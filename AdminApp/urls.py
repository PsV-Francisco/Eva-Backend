from django.urls import path

from . import admin_records
from . import views

app_name = 'administracion'

urlpatterns = [
    path('', views.home, name='home'),
    path('cargos/', views.cargos, name='cargos'),
    path('funciones/', views.funciones, name='funciones'),
    path('cargos-funciones/', views.cargos_funciones, name='cargos-funciones'),
    path('delegaciones/', views.delegaciones, name='delegaciones'),
    path('roles/', views.roles, name='roles'),
    path('items/', views.items, name='items'),
    path('items/metas/', views.metas, name='metas'),
    path('tipos-atencion/', views.tipos_atencion, name='tipos-atencion'),
    path('subatenciones/', views.subatenciones, name='subatenciones'),
    path('parametros/', views.parametros, name='parametros'),
    path('historial/', views.historial, name='historial'),
    path('solicitudes-autorizacion/', views.solicitudes_autorizacion, name='solicitudes-autorizacion'),
    path(
        'auditoria-recuperacion/',
        views.password_reset_audit,
        name='auditoria-recuperacion',
    ),
    path('ausencias/', admin_records.ausencias, name='ausencias'),
    path('ausencias/nueva/', admin_records.ausencia_nueva, name='ausencia-nueva'),
    path(
        'ausencias/<int:ausencia_id>/editar/',
        admin_records.ausencia_editar,
        name='ausencia-editar',
    ),
    path(
        'ausencias/<int:ausencia_id>/eliminar/',
        admin_records.ausencia_eliminar,
        name='ausencia-eliminar',
    ),
    path('ajustes-metas/', admin_records.ajustes_metas, name='ajustes-metas'),
    path('felicitaciones/', admin_records.felicitaciones, name='felicitaciones'),
    path('felicitaciones/nueva/', admin_records.felicitacion_nueva, name='felicitacion-nueva'),
    path(
        'felicitaciones/<int:record_id>/editar/',
        admin_records.felicitacion_editar,
        name='felicitacion-editar',
    ),
    path(
        'felicitaciones/<int:record_id>/eliminar/',
        admin_records.felicitacion_eliminar,
        name='felicitacion-eliminar',
    ),
    path('reclamos/', admin_records.reclamos, name='reclamos'),
    path('reclamos/nuevo/', admin_records.reclamo_nuevo, name='reclamo-nuevo'),
    path(
        'reclamos/<int:record_id>/editar/',
        admin_records.reclamo_editar,
        name='reclamo-editar',
    ),
    path(
        'reclamos/<int:record_id>/eliminar/',
        admin_records.reclamo_eliminar,
        name='reclamo-eliminar',
    ),
    path('hitos/', admin_records.hitos, name='hitos'),
    path('hitos/nuevo/', admin_records.hito_nuevo, name='hito-nuevo'),
    path(
        'hitos/<int:record_id>/editar/',
        admin_records.hito_editar,
        name='hito-editar',
    ),
    path(
        'hitos/<int:record_id>/eliminar/',
        admin_records.hito_eliminar,
        name='hito-eliminar',
    ),
    path('vecinos/', admin_records.vecinos, name='vecinos'),
    path('vecinos/nuevo/', admin_records.vecino_nuevo, name='vecino-nuevo'),
    path(
        'vecinos/<int:vecino_id>/editar/',
        admin_records.vecino_editar,
        name='vecino-editar',
    ),
    path(
        'vecinos/<int:vecino_id>/eliminar/',
        admin_records.vecino_eliminar,
        name='vecino-eliminar',
    ),
    path('informes-generados/', admin_records.informes_generados, name='informes-generados'),
    path('resumen-delegacion/', admin_records.resumen_delegacion, name='resumen-delegacion'),
    path('registros/', admin_records.registros, name='registros'),
    path('registros/nuevo/', admin_records.registro_nuevo, name='registro-nuevo'),
    path(
        'registros/<int:record_id>/editar/',
        admin_records.registro_editar,
        name='registro-editar',
    ),
    path('atenciones-sociales/', admin_records.atenciones_sociales, name='atenciones-sociales'),
    path(
        'atenciones-sociales/nueva/',
        admin_records.atencion_social_nueva,
        name='atencion-social-nueva',
    ),
    path(
        'atenciones-sociales/<int:record_id>/editar/',
        admin_records.atencion_social_editar,
        name='atencion-social-editar',
    ),
    path('compromisos/', admin_records.compromisos, name='compromisos'),
    path('compromisos/nuevo/', admin_records.compromiso_nuevo, name='compromiso-nuevo'),
    path(
        'compromisos/<int:record_id>/editar/',
        admin_records.compromiso_editar,
        name='compromiso-editar',
    ),
    path('juntas/', admin_records.juntas, name='juntas'),
    path('juntas/nueva/', admin_records.junta_nueva, name='junta-nueva'),
    path(
        'juntas/<int:junta_id>/editar/',
        admin_records.junta_editar,
        name='junta-editar',
    ),
    path(
        'juntas/<int:junta_id>/eliminar/',
        admin_records.junta_eliminar,
        name='junta-eliminar',
    ),
]
