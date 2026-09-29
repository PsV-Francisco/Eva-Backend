from django.urls import path

from . import views

app_name = 'delegado'

urlpatterns = [path('', views.home, name='home')]