from django.urls import path

from . import views

app_name = 'coordinador'

urlpatterns = [
    path('', views.home, name='home'),
    path('periodos/', views.periodos, name='periodos'),
    path('metas/', views.metas, name='metas'),
    path('cargos-funciones/', views.cargos_funciones, name='cargos_funciones'),
    path('ponderaciones/', views.ponderaciones, name='ponderaciones'),
    path('informes/', views.informes, name='informes'),
    path('tendencias/', views.tendencias, name='tendencias'),
    path('solicitudes-autorizacion/', views.solicitudes_autorizacion, name='solicitudes_autorizacion'),
]
