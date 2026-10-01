from django.contrib import admin

from .models import Evidencia, RevisionEvidencia


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'registro', 'compromiso', 'supervisor', 'fecha', 'estado')
	list_filter = ('estado', 'fecha')
	search_fields = ('codigo', 'registro__codigo', 'compromiso__descripcion', 'supervisor__email')
	readonly_fields = ('codigo', 'fecha')


@admin.register(RevisionEvidencia)
class RevisionEvidenciaAdmin(admin.ModelAdmin):
	list_display = ('evidencia', 'verificador', 'decision', 'fecha')
	list_filter = ('decision', 'fecha')
	search_fields = ('evidencia__codigo', 'verificador__email', 'observaciones')
	readonly_fields = ('fecha',)
