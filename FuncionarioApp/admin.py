from django.contrib import admin

from .models import (
    AtencionSocial,
    Beneficiado,
    CargoJv,
    CasoSocial,
    GestionAtencion,
    Registro,
    Solicitante,
    Territorio,
)


@admin.register(Territorio)
class TerritorioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'delegacion')
    list_filter = ('delegacion',)
    search_fields = ('nombre', 'delegacion__nombre')


@admin.register(CargoJv)
class CargoJvAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'junta_vecino')
    list_filter = ('junta_vecino',)
    search_fields = ('nombre', 'permisos', 'junta_vecino__nombre')


@admin.register(Beneficiado)
class BeneficiadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'telefono', 'email')
    search_fields = ('nombre', 'apellido', 'telefono', 'email')


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'fecha', 'descripcion', 'autor', 'periodo', 'estado')
	list_filter = ('estado', 'periodo', 'fecha')
	search_fields = ('codigo', 'descripcion', 'accion', 'autor__email')
	readonly_fields = ('codigo', 'creado')


@admin.register(AtencionSocial)
class AtencionSocialAdmin(admin.ModelAdmin):
	list_display = ('solicitante', 'delegacion', 'tipo_atencion', 'usuario', 'fecha', 'creado')
	list_filter = ('delegacion', 'tipo_atencion', 'fecha')
	search_fields = ('usuario__email', 'solicitante__identificador', 'solicitante__nombre', 'tipo_atencion', 'resultado')
	readonly_fields = ('creado',)


@admin.register(Solicitante)
class SolicitanteAdmin(admin.ModelAdmin):
	list_display = ('identificador', 'nombre', 'delegacion')
	list_filter = ('delegacion',)
	search_fields = ('identificador', 'nombre', 'delegacion__nombre')


@admin.register(GestionAtencion)
class GestionAtencionAdmin(admin.ModelAdmin):
	list_display = ('atencion', 'numero_gestion', 'fecha')
	list_filter = ('numero_gestion', 'fecha')
	search_fields = ('atencion__usuario__email', 'observaciones')
	readonly_fields = ('codigo',)


@admin.register(CasoSocial)
class CasoSocialAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'atencion_social')
	readonly_fields = ('codigo',)
