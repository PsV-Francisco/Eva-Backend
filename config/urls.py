from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', views.health, name='health'),
    path('api/roles/', views.roles, name='roles'),
    path('funcionario/', include('FuncionarioApp.urls')),
    path('supervisor/', include('SupervisorApp.urls')),
    path('delegado/', include('DelegadoApp.urls')),
    path('coordinador/', include('CoordinadorApp.urls')),
    path('admin-app/', include('AdminApp.urls')),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]
