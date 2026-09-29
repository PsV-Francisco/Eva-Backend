from django.urls import path

from . import views

app_name = 'coordinador'

urlpatterns = [path('', views.home, name='home')]