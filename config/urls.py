from django.contrib import admin
from django.urls import path, include # se me olvio el inlude, lo agrego para poder incluir las urls de la app_inicio

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_inicio.urls')),
    path('noticias/', include('app_noticias.urls')),
    path('turismo/', include('app_turismo.urls')),
]
