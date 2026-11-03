import secrets
from django.conf import settings
from django.db import models
from FuncionarioApp.models import Tipo,Subtipo

#Modelo : Agenda (OK)
class Agenda(models.Model):

	delegacion = models.ForeignKey('AdminApp.Delegacion',on_delete=models.PROTECT,related_name='agendas',)
	periodo = models.ForeignKey('CoordinadorApp.Periodo',on_delete=models.PROTECT,related_name='agendas',)

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


#Modelo : Compromiso (OK)
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

	#Atributos del Compromiso
	agenda = models.ForeignKey(Agenda, on_delete=models.PROTECT, related_name='compromisos')
	descripcion = models.CharField(max_length=240)
	solicitante = models.CharField(max_length=160, blank=True)
	territorio = models.CharField(max_length=160, blank=True)
	responsable = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='compromisos')
	fecha = models.DateTimeField(db_column='FECHA')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.INGRESADO)
	observaciones = models.TextField(blank=True)
	umbral_minimo = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, db_column='UMBRAL_MINIMO')
	genera_puntaje = models.DecimalField(max_digits=3, decimal_places=1, default=0, db_column='GENERA_PUNTAJE')
	periodo_agenda = models.IntegerField(default=0, db_column='PERIODO_AGENDA')
	delegacion_agenda = models.IntegerField(default=0, db_column='DELEGACION_AGENDA')
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)
	tipo = models.ForeignKey(Tipo,on_delete=models.PROTECT,db_column='TIPO',related_name='Compromiso')
	subtipo = models.ForeignKey(Subtipo,on_delete=models.PROTECT,db_column='SUBTIPO',related_name='Compromiso')

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

	def save(self, *args, **kwargs):
		if self.agenda_id:
			self.periodo_agenda = self.agenda.periodo_id
			self.delegacion_agenda = self.agenda.delegacion_id
		return super().save(*args, **kwargs)

#Modelo : Felicitacion (OK)
class Felicitacion(models.Model):
	evidencia = models.CharField(max_length=1000, db_column='EVIDENCIA')
	fecha = models.DateField(db_column='FECHA')
	ubicacion = models.CharField(max_length=100, db_column='UBICACION')
	estado = models.CharField(max_length=50, db_column='ESTADO')
	desempeno = models.ForeignKey('CoordinadorApp.Desempeno',on_delete=models.PROTECT,db_column='DESEMPEÑO',related_name='felicitaciones',)
	usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,db_column='USUARIO',related_name='felicitaciones',)
	item = models.ForeignKey('CoordinadorApp.Item',on_delete=models.PROTECT,db_column='ITEM',related_name='felicitaciones',)
	periodo = models.ForeignKey('CoordinadorApp.Periodo',on_delete=models.PROTECT,db_column='PERIODO',related_name='felicitaciones',)

	class Meta:
		db_table = 'felicitacion'
		ordering = ['-fecha']
		verbose_name = 'felicitación'
		verbose_name_plural = 'felicitaciones'

#Modelo : Ausencia (OK)
class Ausencia(models.Model):
	fecha = models.DateTimeField(db_column='FECHA')
	descripcion = models.CharField(max_length=800, db_column='DESCRIPCION')
	desempeno = models.ForeignKey('CoordinadorApp.Desempeno',on_delete=models.PROTECT,db_column='DESEMPEÑO',related_name='ausencias',)
	usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,db_column='USUARIO',related_name='ausencias',)
	item = models.ForeignKey('CoordinadorApp.Item',on_delete=models.PROTECT,db_column='ITEM',related_name='ausencias',)
	periodo = models.ForeignKey('CoordinadorApp.Periodo',on_delete=models.PROTECT,db_column='PERIODO',related_name='ausencias',)

	class Meta:
		db_table = 'ausencia'
		ordering = ['-fecha']
		verbose_name = 'ausencia'
		verbose_name_plural = 'ausencias'

#Modelo : Reclamo (OK)
class Reclamo(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'abierto','Abierto'
		CERRADO = 'cerrado','Cerrado'

	evidencia = models.CharField(max_length=100, db_column='EVIDENCIA')
	fecha = models.DateTimeField(null=True, blank=True, db_column='FECHA')
	ubicacion = models.CharField(
		max_length=100, null=True, blank=True, db_column='UBICACION',
	)
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)
	desempeno = models.ForeignKey(
		'CoordinadorApp.Desempeno',
		on_delete=models.PROTECT,
		db_column='DESEMPEÑO',
		related_name='reclamos',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		db_column='USUARIO',
		related_name='reclamos',
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		db_column='ITEM',
		related_name='reclamos',
	)
	periodo = models.ForeignKey(
		'CoordinadorApp.Periodo',
		on_delete=models.PROTECT,
		db_column='PERIODO',
		related_name='reclamos',
	)

	class Meta:
		db_table = 'reclamo'
		ordering = ['-fecha']
		verbose_name = 'reclamo'
		verbose_name_plural = 'reclamos'

#Modelo : Licencia (OK)
class Licencia(models.Model):
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
		db_column='DESEMPEÑO',
		related_name='licencias',
	)
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		db_column='USUARIO',
		related_name='licencias',
	)
	item = models.ForeignKey(
		'CoordinadorApp.Item',
		on_delete=models.PROTECT,
		db_column='ITEM',
		related_name='licencias',
	)

	class Meta:
		db_table = 'licencia'
		ordering = ['-fecha_inicio']
		verbose_name = 'licencia'
		verbose_name_plural = 'licencias'

#Modelo : Hito (OK)
class Hito(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'operativo','Operativo'
		CERRADO = 'cancelado','Cancelado'

	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	descripcion = models.CharField(
		max_length=500, null=True, blank=True, db_column='DESCRIPCION',
	)
	fecha_termino = models.DateTimeField(db_column='FECHA_TERMINO')
	recursos_asociados = models.IntegerField(db_column='RECURSOS_ASOCIADOS')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)
	evento_recurrente = models.SmallIntegerField(db_column='EVENTO_RECURRENTE')
	incluir_agenda = models.SmallIntegerField(db_column='INCLUIR_AGENDA')
	periocidad = models.CharField(max_length=100, db_column='PERIOCIDAD')
	territorio = models.ForeignKey(
		'FuncionarioApp.Territorio',
		on_delete=models.PROTECT,
		db_column='TERRITORIO',
		related_name='hitos',
	)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		db_column='DELEGACION',
		related_name='hitos',
	)
	responsable = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		db_column='RESPONSABLE',
		related_name='hitos_responsable',
	)
	registro = models.ForeignKey(
		'FuncionarioApp.Registro',
		on_delete=models.PROTECT,
		db_column='REGISTRO',
		related_name='hitos',
	)
	autor_registro = models.IntegerField(db_column='AUTOR_REGISTRO')
	item_registro = models.IntegerField(db_column='ITEM_REGISTRO')
	periodo_registro = models.IntegerField(db_column='PERIODO_REGISTRO')

	class Meta:
		db_table = 'hito'
		ordering = ['fecha_termino', 'nombre']
		verbose_name = 'hito'
		verbose_name_plural = 'hitos'

#Modelo : Informe (OK)
class Informe(models.Model):
	tipo = models.CharField(max_length=100, db_column='TIPO')
	filtros = models.CharField(max_length=200, db_column='FILTROS')
	fecha_generacion = models.DateTimeField(db_column='FECHA_GENERACION')
	formato = models.CharField(max_length=100, db_column='FORMATO')
	autor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		db_column='AUTOR',
		related_name='informes',
	)

	class Meta:
		db_table = 'informe'
		ordering = ['-fecha_generacion']
		verbose_name = 'informe'
		verbose_name_plural = 'informes'

#
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
		db_table = 'delegadoapp_historialestadocompromiso'
		ordering = ['-fecha']
		verbose_name = 'historial de estado de compromiso'
		verbose_name_plural = 'historiales de estado de compromiso'

#
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
		db_table = 'delegadoapp_seguimientoacceso'
		ordering = ['-created_at']
		verbose_name = 'acceso a seguimiento público'
		verbose_name_plural = 'accesos a seguimiento público'
