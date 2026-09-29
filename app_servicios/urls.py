from django.urls import path

from . import views

urlpatterns = [
    path('', views.guia_ciudadana, name='guia_ciudadana'),
    path('lugares/', views.lugares_servicios, name='lugares_servicios'),
]
