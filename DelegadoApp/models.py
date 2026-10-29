import secrets

from django.conf import settings
from django.db import models

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
