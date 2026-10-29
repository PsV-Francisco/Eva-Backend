import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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
		'AdminApp.Catalogo', on_delete=models.PROTECT, related_name='registros_catalogo',
		null=True,
	)

	class Meta:
		ordering = ['-fecha', '-creado']
		db_table = "registro"
		verbose_name = "Registro"
		verbose_name_plural = "Registros"

	def __str__(self):
		return f'{self.codigo} - {self.descripcion}'

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de registro es inmutable.')
		return super().save(*args, **kwargs)


#Modelo Atención Social
class Solicitante(models.Model):
	identificador = models.CharField(max_length=32)
	nombre = models.CharField(max_length=160)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='solicitantes',
	)

	class Meta:
		ordering = ['nombre', 'identificador']
		constraints = [
			models.UniqueConstraint(
				fields=['delegacion', 'identificador'],
				name='solicitante_identificador_unico_por_delegacion',
			),
		]
		verbose_name = 'solicitante'
		verbose_name_plural = 'solicitantes'

	def save(self, *args, **kwargs):
		self.identificador = self.identificador.strip().upper()
		self.nombre = self.nombre.strip()
		return super().save(*args, **kwargs)

	def __str__(self):
		return f'{self.nombre} ({self.identificador})'


class AtencionSocial(models.Model):
	usuario = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='atenciones_sociales',
	)
	solicitante = models.ForeignKey(
		Solicitante,
		on_delete=models.PROTECT,
		related_name='atenciones',
		null=True,
		blank=True,
	)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='atenciones_sociales',
		null=True,
		blank=True,
	)
	tipo_atencion = models.CharField(max_length=120)
	tipo_atencion_catalogo = models.ForeignKey(
		'AdminApp.TipoAtencion',
		on_delete=models.PROTECT,
		related_name='atenciones_sociales',
		null=True,
		blank=True,
	)
	sub_atencion = models.ForeignKey(
		'AdminApp.SubAtencion',
		on_delete=models.PROTECT,
		related_name='atenciones_sociales',
		null=True,
		blank=True,
	)
	descripcion = models.TextField(blank=True)
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

	def clean(self):
		errors = {}
		if bool(self.tipo_atencion_catalogo_id) != bool(self.sub_atencion_id):
			errors['sub_atencion'] = 'El tipo y la Sub Atención deben seleccionarse juntos.'
		elif (
			self.tipo_atencion_catalogo_id
			and self.sub_atencion.tipo_atencion_id != self.tipo_atencion_catalogo_id
		):
			errors['sub_atencion'] = 'La Sub Atención no corresponde al tipo seleccionado.'

		if bool(self.solicitante_id) != bool(self.delegacion_id):
			errors['delegacion'] = 'El solicitante y la delegación deben asociarse juntos.'
		elif (
			self.solicitante_id
			and self.solicitante.delegacion_id != self.delegacion_id
		):
			errors['solicitante'] = 'El solicitante no pertenece a la delegación seleccionada.'

		if errors:
			raise ValidationError(errors)


class CasoSocial(models.Model):
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	atencion_social = models.OneToOneField(
		AtencionSocial,
		on_delete=models.CASCADE,
		related_name='caso_social',
	)

	class Meta:
		ordering = ['-atencion_social__fecha', '-pk']
		verbose_name = 'caso social'
		verbose_name_plural = 'casos sociales'

	def __str__(self):
		return f'Caso {self.codigo} - {self.atencion_social.tipo_atencion}'

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de caso social es inmutable.')
		return super().save(*args, **kwargs)


#Modelo Gestion Atención
class GestionAtencion(models.Model):
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de atención es inmutable.')
		return super().save(*args, **kwargs)
