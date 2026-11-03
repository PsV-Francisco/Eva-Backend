import uuid
from django.conf import settings
from django.db import models

#Modelo : Funcion (OK)
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

#Modelo : Item (OK)
class Item(models.Model):
	class Estado(models.TextChoices):
		ACTIVO = 'activo', 'Activo'
		INACTIVO = 'inactivo', 'Inactivo'

	codigo = models.CharField(max_length=20, unique=True, null=True)
	nombre = models.CharField(max_length=120)
	descripcion = models.TextField(blank=True)
	ponderacion = models.DecimalField(max_digits=3,decimal_places=1,null=True,blank=True,db_column='PONDERACION',)
	estado = models.CharField(max_length=20,choices=Estado.choices,default=Estado.ACTIVO,)

	class Meta:
		ordering = ['nombre']
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


#Modelo : CargoFuncion (OK)
class CargoFuncion(models.Model):
	cargo = models.ForeignKey('AdminApp.Cargo',on_delete=models.PROTECT,related_name='asignaciones_funciones',)
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


#Modelo : Periodo (OK)
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


class SolicitudAutorizacionPeriodo(models.Model):
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		CANCELADA = 'cancelada', 'Cancelada'
		REVOCADA = 'revocada', 'Revocada'
		VENCIDA = 'vencida', 'Vencida'

	periodo = models.ForeignKey(
		Periodo,
		on_delete=models.PROTECT,
		related_name='solicitudes_autorizacion',
	)
	solicitante = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='solicitudes_autorizacion_periodo',
	)
	aprobador = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='autorizaciones_periodo_resueltas',
	)
	funcionarios = models.ManyToManyField(
		settings.AUTH_USER_MODEL,
		related_name='autorizaciones_periodo_funcionario',
	)
	alcances = models.JSONField(default=list)
	motivo = models.TextField()
	comentario_aprobador = models.TextField(blank=True)
	estado = models.CharField(
		max_length=16,
		choices=Estado.choices,
		default=Estado.PENDIENTE,
	)
	creada_en = models.DateTimeField(auto_now_add=True)
	decidida_en = models.DateTimeField(null=True, blank=True)
	vence_en = models.DateTimeField(null=True, blank=True)
	usada_en = models.DateTimeField(null=True, blank=True)
	revocada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		db_table = 'solicitud_autorizacion_periodo'
		ordering = ['-creada_en']

	def __str__(self):
		return f'Autorización de {self.periodo} solicitada por {self.solicitante}'


#Modelo : PeriodoSemana (OK)
class PeriodoSemana(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'abierto','Abierto'
		CERRADO = 'cerrado','Cerrado'

	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	fecha_inicio = models.DateTimeField(null=True, blank=True, db_column='FECHA_INICIO')
	fecha_fin = models.DateTimeField(null=True, blank=True, db_column='FECHA_FIN')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)
	periodo = models.ForeignKey('Periodo', on_delete=models.PROTECT, db_column='PERIODO')

	class Meta:
		db_table = 'periodo_semana'
		ordering = ['-fecha_inicio']
		verbose_name = "Semana del Periodo"
		verbose_name_plural = "Semanas del Periodo"

#Modelo : Desempeño (OK)
class Desempeno(models.Model):
	
	usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='desempenos',)
	item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='desempenos')
	meta = models.DecimalField(max_digits=12, decimal_places=2)
	avance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	ultimo_registro = models.DateField(null=True, blank=True)
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='desempenos')
	dias_libres = models.IntegerField(null=True, blank=True, db_column='DIAS_LIBRES')
	vacaciones = models.IntegerField(null=True, blank=True, db_column='VACACIONES')
	dias_adm = models.IntegerField(null=True, blank=True, db_column='DIAS_ADM')

	class Meta:
		ordering = ['periodo', 'usuario', 'item']
		db_table = "desempeño"
		verbose_name = 'Desempeño'
		verbose_name_plural = 'Desempeños'
		constraints = [
			models.UniqueConstraint(
				fields=['usuario', 'item', 'periodo'],
				name='desempeno_unico_por_usuario_item_periodo',
			),
			models.CheckConstraint(condition=models.Q(meta__gt=0), name='desempeno_meta_positiva'),
			models.CheckConstraint(condition=models.Q(avance__gte=0), name='desempeno_avance_no_negativo'),
		]

	def __str__(self):
		return f'{self.usuario} - {self.item} - {self.periodo}'


#Modelo : GestionAtencion (OK)
class GestionAtencion(models.Model):
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	numero_gestion = models.PositiveSmallIntegerField(db_column='NUMERO_GESTION')
	fecha = models.DateField(db_column='FECHA')
	observaciones = models.TextField(blank=True, db_column='OBSERVACIONES')

	class Meta:
		ordering = ['fecha', 'numero_gestion']
		constraints = [
			models.CheckConstraint(
				condition=models.Q(numero_gestion__gte=1, numero_gestion__lte=3),
				name='gestion_numero_entre_1_y_3',
			),
		]
		db_table = 'gestion_atencion'
		verbose_name = 'gestión de atención'
		verbose_name_plural = 'gestiones de atenciones'

	def __str__(self):
		return f'Gestión {self.numero_gestion} - {self.fecha:%Y-%m-%d}'

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de atención es inmutable.')
		return super().save(*args, **kwargs)

#Modelo : AtencionSocial (OK)
class AtencionSocial(models.Model):

	fecha = models.DateTimeField(db_column='FECHA')
	resultado = models.TextField(blank=True)
	observaciones = models.TextField(blank=True)
	autor = models.ForeignKey('AdminApp.Usuario', on_delete=models.PROTECT, db_column='AUTOR')
	beneficiado = models.ForeignKey('FuncionarioApp.Beneficiado', on_delete=models.PROTECT, db_column='BENEFICIADO')
	tipo = models.ForeignKey('FuncionarioApp.Tipo',on_delete=models.PROTECT,db_column='TIPO',related_name='Atencion_Social')
	subtipo = models.ForeignKey('FuncionarioApp.Subtipo',on_delete=models.PROTECT,db_column='SUBTIPO',related_name='Atencion_Social')
	gestion_atencion = models.ForeignKey(GestionAtencion, on_delete=models.PROTECT, db_column='GESTION_ATENCION')
	creado = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-fecha']
		db_table = 'atencion_social'
		verbose_name = 'atención social'
		verbose_name_plural = 'atenciones sociales'

	def __str__(self):
		return f'Atención {self.pk} - {self.tipo}'
