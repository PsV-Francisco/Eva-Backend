from django.urls import path

from . import views

app_name = 'administracion'

urlpatterns = [
    path('', views.home, name='home'),
    path('delegaciones/', views.delegaciones, name='delegaciones'),
    path('roles/', views.roles, name='roles'),
    path('items/', views.items, name='items'),
    path('items/metas/', views.metas, name='metas'),
    path('tipos-atencion/', views.tipos_atencion, name='tipos-atencion'),
    path('subatenciones/', views.subatenciones, name='subatenciones'),
    path('parametros/', views.parametros, name='parametros'),
]