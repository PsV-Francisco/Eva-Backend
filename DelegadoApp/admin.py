from django.contrib import admin

from .models import Agenda, Compromiso


@admin.register(Agenda)
class AgendaAdmin(admin.ModelAdmin):
	list_display = ('delegacion', 'periodo')
	list_filter = ('delegacion', 'periodo')
	search_fields = ('delegacion__nombre', 'periodo__nombre')


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
	list_display = ('descripcion', 'agenda', 'fecha', 'estado')
	list_filter = ('estado', 'agenda__delegacion', 'fecha')
	search_fields = ('descripcion', 'solicitante', 'territorio', 'responsables__email')
	filter_horizontal = ('responsables',)
