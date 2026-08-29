from django.contrib import admin
from django.urls import path, include # se me olvio el inlude, lo agrego para poder incluir las urls de la app_inicio

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_inicio.urls')), # cabros solo porciacaso aca se agregan las otras urls 
]
