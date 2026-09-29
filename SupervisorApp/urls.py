from django.urls import path

from . import views

app_name = 'supervisor'

urlpatterns = [path('', views.home, name='home')]