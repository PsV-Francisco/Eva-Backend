from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app_inicio.urls')), #Envío a las urls de App_inicio
    path('noticias/', include('app_noticias.urls')), #Envío a las urls de App_Noticias
    path('turismo/', include('app_turismo.urls')), #Envío a las urls de App_turismo
    path('guia-ciudadana/', include('app_servicios.urls')), #Envío a las Urls de App_Servicios
]
