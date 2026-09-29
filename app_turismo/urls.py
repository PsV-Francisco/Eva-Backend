from django.urls import path

from . import views

urlpatterns = [
    path('', views.turismo, name='turismo'),
]
