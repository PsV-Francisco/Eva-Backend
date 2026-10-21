from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, reverse_lazy
from . import password_reset, views

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        '',
        auth_views.LoginView.as_view(template_name='config/index.html'),
        name='login',
    ),
    path(
        'accounts/password-reset/',
        password_reset.PasswordResetView.as_view(
            template_name='auth/password_reset_form.html',
            email_template_name='auth/password_reset_email.html',
            subject_template_name='auth/password_reset_subject.txt',
            form_class=password_reset.SolicitudRecuperacionForm,
            success_url=reverse_lazy('password_reset_done'),
            extra_email_context={'domain': settings.PASSWORD_RESET_DOMAIN},
        ),
        name='password_reset',
    ),
    path(
        'accounts/password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='auth/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'accounts/reset/<uidb64>/<token>/',
        password_reset.ConfirmacionRecuperacionView.as_view(
            template_name='auth/password_reset_confirm.html',
            form_class=password_reset.NuevaContrasenaForm,
            success_url=reverse_lazy('password_reset_complete'),
        ),
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
