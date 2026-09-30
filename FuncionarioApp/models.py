import uuid

from django.conf import settings
from django.db import models


class Registro(models.Model):
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		VALIDADA = 'validada', 'Validada'
		OBSERVADA = 'observada', 'Observada'
		ANULADA = 'anulada', 'Anulada'

	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	fecha = models.DateField()
	item = models.ForeignKey('CoordinadorApp.Item', on_delete=models.PROTECT, related_name='registros')
	periodo = models.ForeignKey('CoordinadorApp.Periodo', on_delete=models.PROTECT, related_name='registros')
	descripcion = models.CharField(max_length=240)
	accion = models.TextField()
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.CharField(max_length=24, blank=True)
	autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registros')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
	incluir_en_agenda = models.BooleanField(default=False)
	creado = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-fecha', '-creado']

	def __str__(self):
		return f'{self.codigo} - {self.descripcion}'


class AtencionSocial(models.Model):
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='atenciones_sociales',
	)
	tipo_atencion = models.CharField(max_length=120)
	fecha = models.DateField()
	resultado = models.TextField(blank=True)
	observaciones = models.TextField(blank=True)
	creado = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-fecha']

	def __str__(self):
		return f'Atención {self.pk} - {self.tipo_atencion}'


class GestionAtencion(models.Model):
	atencion = models.ForeignKey(AtencionSocial, on_delete=models.CASCADE, related_name='gestiones')
	numero_gestion = models.PositiveSmallIntegerField()
	fecha = models.DateField()
	resultado = models.TextField(blank=True)
	observaciones = models.TextField(blank=True)

	class Meta:
		ordering = ['atencion', 'numero_gestion']
		constraints = [
			models.UniqueConstraint(
				fields=['atencion', 'numero_gestion'],
				name='gestion_numero_unico_por_atencion',
			),
			models.CheckConstraint(
				condition=models.Q(numero_gestion__gte=1, numero_gestion__lte=3),
				name='gestion_numero_entre_1_y_3',
			),
		]

	def __str__(self):
		return f'Gestión {self.numero_gestion} de atención {self.atencion_id}'
