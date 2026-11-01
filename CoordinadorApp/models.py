from django.conf import settings
from django.db import models

#Modelo Funcion
class Funcion(models.Model):
	class Estado(models.TextChoices):
		ACTIVO = 'activo', 'Activo'
		INACTIVO = 'inactivo', 'Inactivo'

	nombre = models.CharField(max_length=120, unique=True)
	descripcion = models.TextField(blank=True)
	estado = models.CharField(
		max_length=20,
		choices=Estado.choices,
		default=Estado.ACTIVO,
	)

	class Meta:
		ordering = ['nombre']
		db_table = "funcion"
		verbose_name = 'función'
		verbose_name_plural = 'funciones'

	def __str__(self):
		return self.nombre

#Modelo Item
class Item(models.Model):
	class Estado(models.TextChoices):
		ACTIVO = 'activo', 'Activo'
		INACTIVO = 'inactivo', 'Inactivo'

	codigo = models.CharField(max_length=20, unique=True, null=True)
	funcion = models.ForeignKey(Funcion, on_delete=models.PROTECT, related_name='items')
	nombre = models.CharField(max_length=120)
	descripcion = models.TextField(blank=True)
	estado = models.CharField(
		max_length=20,
		choices=Estado.choices,
		default=Estado.ACTIVO,
	)

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

	def save(self, *args, **kwargs):
		if not self.codigo and self.pk is None:
			super().save(*args, **kwargs)
			self.codigo = f'ITEM-{self.pk:04d}'
			super().save(using=kwargs.get('using'), update_fields=['codigo'])
			return
		return super().save(*args, **kwargs)


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
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)

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
class SolicitudAutorizacionPeriodo(models.Model):
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		VENCIDA = 'vencida', 'Vencida'
		REVOCADA = 'revocada', 'Revocada'
		CANCELADA = 'cancelada', 'Cancelada'

	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='solicitudes_autorizacion')
	solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='solicitudes_autorizacion_periodo')
	funcionarios = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='autorizaciones_periodo', blank=True)
	alcances = models.JSONField(default=list)
	motivo = models.TextField()
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
	aprobador = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='decisiones_autorizacion_periodo')
	comentario_aprobador = models.TextField(blank=True)
	creada_en = models.DateTimeField(auto_now_add=True)
	decidida_en = models.DateTimeField(null=True, blank=True)
	vence_en = models.DateTimeField(null=True, blank=True)
	usada_en = models.DateTimeField(null=True, blank=True)
	revocada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ['-creada_en']
		db_table = 'solicitud_autorizacion_periodo'

	def __str__(self):
		return f'{self.periodo} - {self.solicitante}'


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
