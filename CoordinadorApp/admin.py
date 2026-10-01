from django.contrib import admin

from .models import CargoFuncion, Desempeno, Funcion, Item, Periodo


@admin.register(Funcion)
class FuncionAdmin(admin.ModelAdmin):
	list_display = ('nombre',)
	search_fields = ('nombre', 'descripcion')


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'funcion')
	list_filter = ('funcion',)
	search_fields = ('nombre', 'funcion__nombre')


@admin.register(CargoFuncion)
class CargoFuncionAdmin(admin.ModelAdmin):
	list_display = ('cargo', 'funcion')
	list_filter = ('funcion',)
	search_fields = ('cargo__nombre', 'funcion__nombre')


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'fecha_inicio', 'fecha_fin', 'estado')
	list_filter = ('estado',)
	search_fields = ('nombre',)


@admin.register(Desempeno)
class DesempenoAdmin(admin.ModelAdmin):
	list_display = ('usuario', 'funcion', 'item', 'periodo', 'meta', 'avance', 'ponderacion')
	list_filter = ('periodo', 'funcion', 'item')
	search_fields = ('usuario__email', 'item__nombre', 'funcion__nombre')
