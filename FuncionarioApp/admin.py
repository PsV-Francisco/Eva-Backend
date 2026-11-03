from django.contrib import admin

from CoordinadorApp.models import AtencionSocial,GestionAtencion
from FuncionarioApp.models import CargoJv,Beneficiado,Registro,Territorio


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
	list_display = ('beneficiado', 'autor', 'tipo', 'subtipo', 'gestion_atencion', 'fecha', 'creado')
	list_filter = ('tipo', 'subtipo', 'fecha')
	search_fields = ('autor__email', 'beneficiado__nombre', 'beneficiado__apellido', 'resultado')
	readonly_fields = ('creado',)



@admin.register(GestionAtencion)
class GestionAtencionAdmin(admin.ModelAdmin):
	list_display = ('numero_gestion', 'fecha', 'observaciones')
	list_filter = ('numero_gestion', 'fecha')
	search_fields = ('observaciones',)
	readonly_fields = ('codigo',)

