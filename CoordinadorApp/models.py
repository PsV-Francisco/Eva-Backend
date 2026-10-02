from django.conf import settings
from django.db import models

#Modelo Funcion
class Funcion(models.Model):
	nombre = models.CharField(max_length=120, unique=True)
	descripcion = models.TextField(blank=True)

	class Meta:
		ordering = ['nombre']
		db_table = "funcion"
		verbose_name = 'función'
		verbose_name_plural = 'funciones'

	def __str__(self):
		return self.nombre

#Modelo Item
class Item(models.Model):
	funcion = models.ForeignKey(Funcion, on_delete=models.PROTECT, related_name='items')
	nombre = models.CharField(max_length=120)
	descripcion = models.TextField(blank=True)

	class Meta:
		ordering = ['funcion__nombre', 'nombre']
		constraints = [
			models.UniqueConstraint(fields=['funcion', 'nombre'], name='item_nombre_unico_por_funcion'),
		]
		db_table = "item"
		verbose_name = 'Item'
		verbose_name_plural = 'Items'

	def __str__(self):
		return self.nombre


#Modelo CargoFuncion
class CargoFuncion(models.Model):
	cargo = models.ForeignKey(
		'AdminApp.Cargo',
		on_delete=models.PROTECT,
		related_name='asignaciones_funciones',
	)
	funcion = models.ForeignKey(Funcion, on_delete=models.PROTECT, related_name='asignaciones_cargos')

	class Meta:
		ordering = ['cargo']
		db_table = "cargo_funcion"
		verbose_name = 'CargoFuncion'
		verbose_name_plural = 'Funciones por cargo'
		constraints = [
			models.UniqueConstraint(fields=['cargo', 'funcion'], name='cargo_funcion_unicos'),
		]

	def __str__(self):
		return f'{self.cargo} - {self.funcion}'


#Modelo Periodo
class Periodo(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'abierto', 'Abierto'
		CERRADO = 'cerrado', 'Cerrado'

	nombre = models.CharField(max_length=120, unique=True)
	fecha_inicio = models.DateField()
	fecha_fin = models.DateField()
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.CERRADO)

	class Meta:
		ordering = ['-fecha_inicio']
		db_table = "periodo"
		verbose_name = 'Periodo'
		verbose_name_plural = 'Periodos'
		constraints = [
			models.CheckConstraint(
				condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')),
				name='periodo_fecha_fin_despues_inicio',
			),
		]

	def __str__(self):
		return self.nombre

#Modelo Desempeño
class Desempeno(models.Model):
	
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='desempenos',
	)
	funcion = models.ForeignKey(
		Funcion, on_delete=models.PROTECT, related_name='desempenos', null=True, blank=True
	)
	item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='desempenos')
	meta = models.DecimalField(max_digits=12, decimal_places=2)
	avance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	ponderacion = models.DecimalField(max_digits=5, decimal_places=2)
	ultimo_registro = models.DateField(null=True, blank=True)
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='desempenos')

	class Meta:
		ordering = ['periodo', 'usuario', 'item','funcion']
		db_table = "desempeño"
		verbose_name = 'Desempeño'
		verbose_name_plural = 'Desempeños'
		constraints = [
			models.UniqueConstraint(
				fields=['usuario', 'item', 'periodo','funcion'],
				name='desempeno_unico_por_usuario_item_periodo',
			),
			models.CheckConstraint(condition=models.Q(meta__gt=0), name='desempeno_meta_positiva'),
			models.CheckConstraint(condition=models.Q(avance__gte=0), name='desempeno_avance_no_negativo'),
			models.CheckConstraint(
				condition=models.Q(ponderacion__gte=0, ponderacion__lte=100),
				name='desempeno_ponderacion_entre_0_y_100',
			),
		]

	def __str__(self):
		return f'{self.usuario} - {self.item} - {self.periodo}'
