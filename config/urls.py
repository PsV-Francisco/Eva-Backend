from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', auth_views.LoginView.as_view(template_name='config/index.html'), name='login'),
    path('inicio/', views.home_redirect, name='home'),
    path('accounts/logout/',auth_views.LogoutView.as_view(next_page='/'),name='logout'),
    path('funcionario/', include('FuncionarioApp.urls')),
    path('supervisor/', include('SupervisorApp.urls')),
    path('delegado/', include('DelegadoApp.urls')),
    path('coordinador/', include('CoordinadorApp.urls')),
    path('admin-app/', include('AdminApp.urls')),
    path('consulta/', include('VistaFApp.urls')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
