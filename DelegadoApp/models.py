from django.conf import settings
from django.db import models


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
	nombre = models.CharField(max_length=120, default='Agenda colectiva')

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['delegacion', 'periodo'], name='agenda_unica_por_delegacion_periodo'),
		]

	def __str__(self):
		return f'{self.nombre} - {self.delegacion} - {self.periodo}'


class Compromiso(models.Model):
	class Estado(models.TextChoices):
		INGRESADO = 'ingresado', 'Ingresado'
		PENDIENTE = 'pendiente', 'Pendiente'
		EN_PROCESO = 'en_proceso', 'En proceso'
		REALIZADO = 'realizado', 'Realizado'

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

	class Meta:
		ordering = ['fecha', 'descripcion']

	def __str__(self):
		return self.descripcion
