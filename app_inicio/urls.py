from django.urls import path
from app_inicio import views

#urls principales
urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('about/', views.about, name='about'),
]