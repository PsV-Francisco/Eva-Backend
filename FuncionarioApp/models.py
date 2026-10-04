import uuid

from django.conf import settings
from django.db import models

#Modelo del Registro
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
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.IntegerField(blank=True, null=True)
	accion = models.TextField(blank=True)
	autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registros')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
	incluir_en_agenda = models.BooleanField(default=False)
	creado = models.DateTimeField(auto_now_add=True)
	catalogo = models.ForeignKey(
		'AdminApp.Catalogo', on_delete=models.CASCADE, related_name='registros_catalogo',
		null=True,
	)

	class Meta:
		ordering = ['-fecha', '-creado']
		db_table = "registro"
		verbose_name = "Registro"
		verbose_name_plural = "Registros"

	def __str__(self):
		return f'{self.codigo} - {self.descripcion}'


#Modelo Atención Social
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
		db_table = "atencion_social"
		verbose_name = "Atención_Social"
		verbose_name_plural = "Atenciones_Sociales"

	def __str__(self):
		return f'Atención {self.pk} - {self.tipo_atencion}'

#Modelo Gestion Atención
class GestionAtencion(models.Model):
	atencion = models.ForeignKey(AtencionSocial, on_delete=models.CASCADE, related_name='gestiones')
	numero_gestion = models.PositiveSmallIntegerField()
	fecha = models.DateField()
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
		db_table = "gestion_atencion"
		verbose_name = "Gestión Atención"
		verbose_name_plural = "Gestión de Atenciones"

	def __str__(self):
		return f'Gestión {self.numero_gestion} de atención {self.atencion}'
