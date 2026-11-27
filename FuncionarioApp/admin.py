from django.contrib import admin
from CoordinadorApp.models import AtencionSocial,GestionAtencion
from FuncionarioApp.models import CargoJv,Registro,Territorio,Vecino


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




@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'fecha', 'descripcion', 'autor', 'periodo', 'estado')
	list_filter = ('estado', 'periodo', 'fecha')
	search_fields = ('codigo', 'descripcion', 'accion', 'autor__email')
	readonly_fields = ('codigo', 'creado')


@admin.register(AtencionSocial)
class AtencionSocialAdmin(admin.ModelAdmin):
	list_display = ('vecino', 'autor', 'tipo', 'subtipo', 'gestion_atencion', 'fecha', 'creado')
	list_filter = ('tipo', 'subtipo', 'fecha')
	search_fields = ('autor__email', 'vecino__nombre', 'vecino__apellido', 'resultado')
	readonly_fields = ('creado',)



@admin.register(GestionAtencion)
class GestionAtencionAdmin(admin.ModelAdmin):
	list_display = ('fecha', 'observaciones',)
	list_filter = ('fecha',)
	search_fields = ('observaciones',)
	readonly_fields = ('codigo',)

@admin.register(Vecino)
class VecinoAdmin(admin.ModelAdmin):
    list_display = ('rut', 'nombre', 'telefono', 'delegacion', 'territorio', 'estado', 'activo')
    list_filter = ('estado', 'activo', 'delegacion', 'territorio')
    search_fields = ('rut', 'nombre', 'telefono', 'direccion')
    readonly_fields = ('creado', 'actualizado')

