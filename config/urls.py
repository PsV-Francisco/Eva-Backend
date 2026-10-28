from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView
from . import delegations, password_reset, views

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        '',
        auth_views.LoginView.as_view(
            template_name='config/index.html',
            authentication_form=password_reset.FormularioAcceso,
        ),
        name='login',
    ),
    path(
        'accounts/password-reset/',
        password_reset.solicitar_recuperacion,
        name='password_reset',
    ),
    path(
        'accounts/password-reset/code/',
        password_reset.verificar_codigo,
        name='password_reset_code',
    ),
    path(
        'accounts/password-reset/new/',
        password_reset.nueva_contrasena,
        name='password_reset_new',
    ),
    path(
        'accounts/password-reset/done/',
        TemplateView.as_view(
            template_name='auth/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'accounts/reset/<uidb64>/<token>/',
        password_reset.confirmar_enlace_recuperacion,
        name='password_reset_confirm',
    ),
    path(
        'accounts/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='auth/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('inicio/', views.home_redirect, name='home'),
    path(
        'delegacion/activa/',
        delegations.select_active_delegation,
        name='select_active_delegation',
    ),
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
