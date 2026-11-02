from django.contrib import admin

from .models import (
    Agenda,
    Ausencia,
    Compromiso,
    Felicitacion,
    Hito,
    Informe,
    Licencia,
    Reclamo,
)


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


@admin.register(Hito)
class HitoAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'fecha_termino', 'territorio', 'delegacion', 'responsable')
	list_filter = ('estado', 'delegacion', 'fecha_termino')
	search_fields = ('nombre', 'descripcion', 'responsable__email', 'registro__descripcion')
	readonly_fields = ('delegacion', 'autor_registro', 'item_registro', 'periodo_registro')


@admin.register(Felicitacion)
class FelicitacionAdmin(admin.ModelAdmin):
	list_display = ('fecha', 'usuario', 'item', 'periodo', 'estado')
	list_filter = ('estado', 'periodo', 'fecha')
	search_fields = ('evidencia', 'usuario__email', 'item__nombre')
	readonly_fields = ('usuario', 'item', 'periodo')


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
	list_display = ('fecha', 'usuario', 'item', 'periodo')
	list_filter = ('periodo', 'fecha')
	search_fields = ('descripcion', 'usuario__email', 'item__nombre')
	readonly_fields = ('usuario', 'item', 'periodo')


@admin.register(Reclamo)
class ReclamoAdmin(admin.ModelAdmin):
	list_display = ('fecha', 'usuario', 'item', 'periodo', 'estado')
	list_filter = ('estado', 'periodo', 'fecha')
	search_fields = ('evidencia', 'usuario__email', 'item__nombre')
	readonly_fields = ('usuario', 'item', 'periodo')


@admin.register(Licencia)
class LicenciaAdmin(admin.ModelAdmin):
	list_display = ('tipo', 'fecha_inicio', 'fecha_fin', 'usuario', 'item')
	list_filter = ('tipo', 'fecha_inicio', 'fecha_fin')
	search_fields = ('tipo', 'descripcion', 'usuario__email', 'item__nombre')
	readonly_fields = ('usuario', 'item')


@admin.register(Informe)
class InformeAdmin(admin.ModelAdmin):
	list_display = ('tipo', 'fecha_generacion', 'formato', 'autor')
	list_filter = ('tipo', 'formato', 'fecha_generacion')
	search_fields = ('tipo', 'filtros', 'autor__email')
