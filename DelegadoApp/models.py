import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def _copy_desempeno_relations(instance, field_names):
	if instance.desempeno_id:
		desempeno = instance.desempeno
		for field_name in field_names:
			setattr(instance, f'{field_name}_id', getattr(desempeno, f'{field_name}_id'))


def _include_update_fields(kwargs, field_names):
	update_fields = kwargs.get('update_fields')
	if update_fields is not None:
		kwargs['update_fields'] = set(update_fields).union(field_names)


def _validate_desempeno_relations(instance, field_names):
	if not instance.desempeno_id:
		return
	desempeno = instance.desempeno
	errors = {
		field_name: 'Debe coincidir con el desempeño relacionado.'
		for field_name in field_names
		if getattr(instance, f'{field_name}_id') != getattr(desempeno, f'{field_name}_id')
	}
	if errors:
		raise ValidationError(errors)


#Modelo de Agenda
class Agenda(models.Model):
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='agendas',
	)
	periodo = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		related_name='agendas',
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['delegacion', 'periodo'], name='agenda_unica_por_delegacion_periodo'),
		]
		db_table = "agenda"
		verbose_name = "Agenda"
		verbose_name_plural = "Agendas"
		ordering = ['delegacion']

	def __str__(self):
		return f'{self.delegacion} - {self.periodo}'


#Modelo de Compromiso
class Compromiso(models.Model):
	class Estado(models.TextChoices):
		INGRESADO = 'ingresado', 'Ingresado'
		PENDIENTE = 'pendiente', 'Pendiente'
		EN_PROCESO = 'en_proceso', 'En proceso'
		REALIZADO = 'realizado', 'Realizado'

	# Identificador público y no secuencial para seguimiento sin login.
	seguimiento_token = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True)
	seguimiento_activo = models.BooleanField(default=True)
	seguimiento_expira = models.DateTimeField(null=True, blank=True)
	seguimiento_ultima_vista = models.DateTimeField(null=True, blank=True)

	agenda = models.ForeignKey(Agenda, on_delete=models.PROTECT, related_name='compromisos')
	descripcion = models.CharField(max_length=240)
	solicitante = models.CharField(max_length=160, blank=True)
	territorio = models.CharField(max_length=160, blank=True)
	responsables = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='compromisos')
	fecha = models.DateField()
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.INGRESADO)
	observaciones = models.TextField(blank=True)
	umbral_minimo = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-fecha', 'descripcion']
		db_table = "compromiso"
		verbose_name = "Compromiso"
		verbose_name_plural = "Compromisos"

	@property
	def codigo_publico(self):
		return f'COM-{self.pk:06d}'

	def generar_token_seguimiento(self):
		if self.seguimiento_token and self.seguimiento_activo:
			return self.seguimiento_token
		while True:
			token = secrets.token_urlsafe(32)
			if not Compromiso.objects.filter(seguimiento_token=token).exclude(pk=self.pk).exists():
				self.seguimiento_token = token
				self.seguimiento_activo = True
				self.seguimiento_expira = None
				return token

	def activar_seguimiento(self):
		if not self.seguimiento_token:
			self.generar_token_seguimiento()
		self.seguimiento_activo = True
		return self.seguimiento_token

	def desactivar_seguimiento(self):
		self.seguimiento_activo = False
		return self.seguimiento_token

	def __str__(self):
		return self.descripcion


class Hito(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	descripcion = models.CharField(
		max_length=500, null=True, blank=True, db_column='DESCRIPCION',
	)
	fecha_termino = models.DateTimeField(db_column='FECHA_TERMINO')
	recursos_asociados = models.IntegerField(db_column='RECURSOS_ASOCIADOS')
	estado = models.CharField(max_length=50, db_column='ESTADO')
	evento_recurrente = models.BooleanField(db_column='EVENTO_RECURRENTE')
	incluir_agenda = models.BooleanField(db_column='INCLUIR_AGENDA')
	periocidad = models.CharField(max_length=100, db_column='PERIOCIDAD')
	territorio = models.ForeignKey(
		'FuncionarioApp.Territorio',
		on_delete=models.PROTECT,
		related_name='hitos',
		db_column='TERRITORIO',
	)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='hitos',
		db_column='DELEGACION',
		editable=False,
	)
	responsable = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='hitos_responsable',
		db_column='RESPONSABLE',
	)
	registro = models.ForeignKey(
		'FuncionarioApp.Registro',
		on_delete=models.PROTECT,
		related_name='hitos',
		db_column='REGISTRO',
	)
	autor_registro = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='hitos_autor_registro',
		db_column='AUTOR_REGISTRO',
		editable=False,
	)
	item_registro = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		related_name='hitos_registro',
		db_column='ITEM_REGISTRO',
		editable=False,
	)
	periodo_registro = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		related_name='hitos_registro',
		db_column='PERIODO_REGISTRO',
		editable=False,
	)

	class Meta:
		db_table = 'hito'
		ordering = ['fecha_termino', 'nombre']
		verbose_name = 'hito'
		verbose_name_plural = 'hitos'

	def clean(self):
		super().clean()
		errors = {}
		if self.registro_id:
			registro = self.registro
			expected = {
				'autor_registro': registro.autor_id,
				'item_registro': registro.item_id,
				'periodo_registro': registro.periodo_id,
			}
			for field_name, expected_id in expected.items():
				if getattr(self, f'{field_name}_id') != expected_id:
					errors[field_name] = 'Debe coincidir con el registro relacionado.'
		if self.territorio_id and self.delegacion_id:
			if self.territorio.delegacion_id != self.delegacion_id:
				errors['delegacion'] = 'Debe coincidir con la delegación del territorio.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		if self.registro_id:
			registro = self.registro
			self.autor_registro_id = registro.autor_id
			self.item_registro_id = registro.item_id
			self.periodo_registro_id = registro.periodo_id
		if self.territorio_id:
			self.delegacion_id = self.territorio.delegacion_id
		derived_fields = ('delegacion', 'autor_registro', 'item_registro', 'periodo_registro')
		_include_update_fields(kwargs, derived_fields)
		self.clean()
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre


class Felicitacion(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	evidencia = models.CharField(max_length=1000, db_column='EVIDENCIA')
	fecha = models.DateField(db_column='FECHA')
	ubicacion = models.CharField(max_length=255, db_column='UBICACION')
	estado = models.CharField(max_length=50, db_column='ESTADO')
	desempeno = models.ForeignKey(
		'CoordinadorApp.Desempeno',
		on_delete=models.PROTECT,
		related_name='felicitaciones',
		db_column='DESEMPEÑO',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='felicitaciones',
		db_column='USUARIO',
		editable=False,
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		related_name='felicitaciones',
		db_column='ITEM',
		editable=False,
	)
	periodo = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		related_name='felicitaciones',
		db_column='PERIODO',
		editable=False,
	)

	class Meta:
		db_table = 'felicitacion'
		verbose_name = 'felicitación'
		verbose_name_plural = 'felicitaciones'

	def clean(self):
		super().clean()
		_validate_desempeno_relations(self, ('usuario', 'item', 'periodo'))

	def save(self, *args, **kwargs):
		derived_fields = ('usuario', 'item', 'periodo')
		_copy_desempeno_relations(self, derived_fields)
		_include_update_fields(kwargs, derived_fields)
		self.clean()
		return super().save(*args, **kwargs)

	def __str__(self):
		return f'Felicitación {self.pk}'


class Ausencia(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	fecha = models.DateTimeField(db_column='FECHA')
	descripcion = models.CharField(max_length=800, db_column='DESCRIPCION')
	desempeno = models.ForeignKey(
		'CoordinadorApp.Desempeno',
		on_delete=models.PROTECT,
		related_name='ausencias',
		db_column='DESEMPEÑO',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='ausencias',
		db_column='USUARIO',
		editable=False,
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		related_name='ausencias',
		db_column='ITEM',
		editable=False,
	)
	periodo = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		related_name='ausencias',
		db_column='PERIODO',
		editable=False,
	)

	class Meta:
		db_table = 'ausencia'
		verbose_name = 'ausencia'
		verbose_name_plural = 'ausencias'

	def clean(self):
		super().clean()
		_validate_desempeno_relations(self, ('usuario', 'item', 'periodo'))

	def save(self, *args, **kwargs):
		derived_fields = ('usuario', 'item', 'periodo')
		_copy_desempeno_relations(self, derived_fields)
		_include_update_fields(kwargs, derived_fields)
		self.clean()
		return super().save(*args, **kwargs)

	def __str__(self):
		return f'Ausencia {self.pk}'


class Reclamo(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	evidencia = models.CharField(max_length=1000, db_column='EVIDENCIA')
	fecha = models.DateTimeField(null=True, blank=True, db_column='FECHA')
	ubicacion = models.CharField(
		max_length=255, null=True, blank=True, db_column='UBICACION',
	)
	estado = models.CharField(max_length=50, null=True, blank=True, db_column='ESTADO')
	desempeno = models.ForeignKey(
		'CoordinadorApp.Desempeno',
		on_delete=models.PROTECT,
		related_name='reclamos',
		db_column='DESEMPEÑO',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='reclamos',
		db_column='USUARIO',
		editable=False,
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		related_name='reclamos',
		db_column='ITEM',
		editable=False,
	)
	periodo = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		related_name='reclamos',
		db_column='PERIODO',
		editable=False,
	)

	class Meta:
		db_table = 'reclamo'
		verbose_name = 'reclamo'
		verbose_name_plural = 'reclamos'

	def clean(self):
		super().clean()
		_validate_desempeno_relations(self, ('usuario', 'item', 'periodo'))

	def save(self, *args, **kwargs):
		derived_fields = ('usuario', 'item', 'periodo')
		_copy_desempeno_relations(self, derived_fields)
		_include_update_fields(kwargs, derived_fields)
		self.clean()
		return super().save(*args, **kwargs)

	def __str__(self):
		return f'Reclamo {self.pk}'


class Licencia(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	fecha_inicio = models.DateTimeField(db_column='FECHA_INICIO')
	fecha_fin = models.DateTimeField(db_column='FECHA_FIN')
	tipo = models.CharField(max_length=45, null=True, blank=True, db_column='TIPO')
	descripcion = models.CharField(
		max_length=500, null=True, blank=True, db_column='DESCRIPCION',
	)
	archivo = models.CharField(max_length=1000, db_column='ARCHIVO')
	desempeno = models.ForeignKey(
		'CoordinadorApp.Desempeno',
		on_delete=models.PROTECT,
		related_name='licencias',
		db_column='DESEMPEÑO',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='licencias',
		db_column='USUARIO',
		editable=False,
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		related_name='licencias',
		db_column='ITEM',
		editable=False,
	)

	class Meta:
		db_table = 'licencia'
		ordering = ['-fecha_inicio']
		verbose_name = 'licencia'
		verbose_name_plural = 'licencias'

	def clean(self):
		super().clean()
		_validate_desempeno_relations(self, ('usuario', 'item'))

	def save(self, *args, **kwargs):
		derived_fields = ('usuario', 'item')
		_copy_desempeno_relations(self, derived_fields)
		_include_update_fields(kwargs, derived_fields)
		self.clean()
		return super().save(*args, **kwargs)

	def __str__(self):
		return f'Licencia {self.pk}'


class Informe(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	tipo = models.CharField(max_length=100, db_column='TIPO')
	filtros = models.TextField(db_column='FILTROS')
	fecha_generacion = models.DateTimeField(db_column='FECHA_GENERACION')
	formato = models.CharField(max_length=100, db_column='FORMATO')
	autor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='informes',
		db_column='AUTOR',
	)

	class Meta:
		db_table = 'informe'
		ordering = ['-fecha_generacion']
		verbose_name = 'informe'
		verbose_name_plural = 'informes'

	def __str__(self):
		return f'{self.tipo} ({self.fecha_generacion:%Y-%m-%d})'


class HistorialEstadoCompromiso(models.Model):
	compromiso = models.ForeignKey(
		Compromiso,
		on_delete=models.CASCADE,
		related_name='historial_estados',
	)
	estado_anterior = models.CharField(max_length=16, blank=True)
	estado_nuevo = models.CharField(max_length=16, choices=Compromiso.Estado.choices)
	autor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='cambios_estado_compromiso',
	)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-fecha']
		verbose_name = 'historial de estado de compromiso'
		verbose_name_plural = 'historiales de estado de compromiso'


class SeguimientoAcceso(models.Model):
	compromiso = models.ForeignKey(
		Compromiso,
		on_delete=models.SET_NULL,
		related_name='seguimiento_accesos',
		null=True,
		blank=True,
	)
	token = models.CharField(max_length=64, blank=True, db_index=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.CharField(max_length=255, blank=True)
	exito = models.BooleanField(default=False)
	motivo = models.CharField(max_length=32, choices=(
		('valido', 'Válido'),
		('invalido', 'Inválido'),
		('desactivado', 'Desactivado'),
		('vencido', 'Vencido'),
		('limitado', 'Limitado por IP'),
	), default='valido')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'acceso a seguimiento público'
		verbose_name_plural = 'accesos a seguimiento público'
