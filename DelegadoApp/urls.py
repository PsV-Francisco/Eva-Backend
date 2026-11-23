from django.urls import path
from . import views

app_name = 'delegado'

urlpatterns = [
    path('', views.home, name='home'),
    path('resumen/', views.resumen, name='resumen'),
    # Ruta pública accesible por solicitantes externos
    path('seguimiento/<str:token>/', views.seguimiento_publico, name='seguimiento_publico'),
]