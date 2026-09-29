from django.urls import path

from . import views

app_name = 'administracion'

urlpatterns = [path('', views.home, name='home')]