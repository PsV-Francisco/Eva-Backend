from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='AdminApp/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('api/health/', views.health, name='health'),
    path('api/roles/', views.roles, name='roles'),
    path('funcionario/', include('FuncionarioApp.urls')),
    path('supervisor/', include('SupervisorApp.urls')),
    path('delegado/', include('DelegadoApp.urls')),
    path('coordinador/', include('CoordinadorApp.urls')),
    path('admin-app/', include('AdminApp.urls')),
    path('consulta/', include('VistaFApp.urls')),
    path('', views.home_redirect, name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
