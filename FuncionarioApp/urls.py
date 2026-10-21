from django.urls import path

from . import views

app_name = 'funcionario'

urlpatterns = [
    path('', views.home, name='home'),
    path('cumplimiento/', views.cumplimiento, name='cumplimiento'),
    path('atencion-social/', views.atencion_social, name='atencion_social'),
    path('agenda-colectiva/', views.agenda_colectiva, name='agenda_colectiva'),
]