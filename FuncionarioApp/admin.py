from django.contrib import admin

from .models import AtencionSocial, GestionAtencion, Registro


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'fecha', 'descripcion', 'autor', 'periodo', 'estado')
	list_filter = ('estado', 'periodo', 'fecha')
	search_fields = ('codigo', 'descripcion', 'accion', 'autor__email')
	readonly_fields = ('codigo', 'creado')


@admin.register(AtencionSocial)
class AtencionSocialAdmin(admin.ModelAdmin):
	list_display = ('usuario', 'tipo_atencion', 'fecha', 'creado')
	list_filter = ('tipo_atencion', 'fecha')
	search_fields = ('usuario__email', 'tipo_atencion', 'resultado')
	readonly_fields = ('creado',)


@admin.register(GestionAtencion)
class GestionAtencionAdmin(admin.ModelAdmin):
	list_display = ('atencion', 'numero_gestion', 'fecha')
	list_filter = ('numero_gestion', 'fecha')
	search_fields = ('atencion__usuario__email', 'resultado')
