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
    path('felicitaciones/', admin_records.felicitaciones, name='felicitaciones'),
    path('reclamos/', admin_records.reclamos, name='reclamos'),
    path('hitos/', admin_records.hitos, name='hitos'),
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
    path('atenciones-sociales/', admin_records.atenciones_sociales, name='atenciones-sociales'),
    path('compromisos/', admin_records.compromisos, name='compromisos'),
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
