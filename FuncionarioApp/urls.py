from django.urls import path

from . import views

app_name = 'funcionario'

urlpatterns = [path('', views.home, name='home')]