from django.contrib import admin

from .models import CargoFuncion, Desempeno, Funcion, Item, Periodo, PeriodoSemana


@admin.register(Funcion)
class FuncionAdmin(admin.ModelAdmin):
	list_display = ('nombre',)
	search_fields = ('nombre', 'descripcion')


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre','estado')
	list_filter = ('estado',)
	search_fields = ('codigo', 'nombre', 'descripcion')


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


@admin.register(PeriodoSemana)
class PeriodoSemanaAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'periodo', 'fecha_inicio', 'fecha_fin', 'estado')
	list_filter = ('periodo', 'estado')
	search_fields = ('nombre', 'periodo__nombre')


@admin.register(Desempeno)
class DesempenoAdmin(admin.ModelAdmin):
	list_display = ('usuario', 'item', 'periodo', 'meta', 'avance', 'ultimo_registro')
	list_filter = ('periodo', 'item')
	search_fields = ('usuario__email', 'item__nombre')
