import uuid
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def normalizar_telefono(value):
	return re.sub(r'\D', '', value or '')

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


class Vecino(models.Model):
	nombre = models.CharField(max_length=160)
	telefono = models.CharField(max_length=32)
	direccion = models.CharField(max_length=255, blank=True)
	territorio = models.CharField(max_length=160)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='vecinos',
	)
	solicitante = models.OneToOneField(
		Solicitante,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='vecino',
	)
	activo = models.BooleanField(default=True)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['nombre', 'pk']
		indexes = [
			models.Index(fields=['delegacion', 'activo', 'nombre']),
			models.Index(fields=['delegacion', 'telefono']),
		]
		verbose_name = 'vecino'
		verbose_name_plural = 'vecinos'

	def clean(self):
		errors = {}
		self.nombre = self.nombre.strip()
		self.telefono = self.telefono.strip()
		self.territorio = self.territorio.strip()
		if len(self.nombre) < 2:
			errors['nombre'] = 'Ingresa un nombre válido.'
		phone_digits = normalizar_telefono(self.telefono)
		if not 7 <= len(phone_digits) <= 15:
			errors['telefono'] = 'Ingresa un teléfono válido.'
		if not self.territorio:
			errors['territorio'] = 'Ingresa un territorio.'
		if self.solicitante_id and self.solicitante.delegacion_id != self.delegacion_id:
			errors['solicitante'] = 'El solicitante debe pertenecer a la misma delegación.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		self.nombre = self.nombre.strip()
		self.telefono = self.telefono.strip()
		self.territorio = self.territorio.strip()
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre


class JuntaVecinos(models.Model):
	nombre = models.CharField(max_length=160)
	domicilio_legal = models.CharField(max_length=255)
	territorio = models.CharField(max_length=160)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='juntas_vecinos',
	)
	cantidad_socios_activos = models.PositiveIntegerField(null=True, blank=True)
	fecha_constitucion = models.DateField()
	numero_personalidad_juridica = models.CharField(max_length=80)
	fecha_inscripcion = models.DateField()
	numero_registro = models.CharField(max_length=80)
	activo = models.BooleanField(default=True)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['nombre', 'pk']
		indexes = [
			models.Index(fields=['delegacion', 'activo', 'nombre']),
			models.Index(fields=['numero_personalidad_juridica']),
		]
		verbose_name = 'junta de vecinos'
		verbose_name_plural = 'juntas de vecinos'

	def clean(self):
		errors = {}
		self.nombre = self.nombre.strip()
		self.domicilio_legal = self.domicilio_legal.strip()
		self.territorio = self.territorio.strip()
		self.numero_personalidad_juridica = self.numero_personalidad_juridica.strip()
		self.numero_registro = self.numero_registro.strip()
		if len(self.nombre) < 2:
			errors['nombre'] = 'Ingresa un nombre válido.'
		if self.cantidad_socios_activos is not None and self.cantidad_socios_activos < 0:
			errors['cantidad_socios_activos'] = 'La cantidad no puede ser negativa.'
		if self.fecha_inscripcion and self.fecha_constitucion and self.fecha_inscripcion < self.fecha_constitucion:
			errors['fecha_inscripcion'] = 'La inscripción no puede ser anterior a la constitución.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		self.nombre = self.nombre.strip()
		self.domicilio_legal = self.domicilio_legal.strip()
		self.territorio = self.territorio.strip()
		self.numero_personalidad_juridica = self.numero_personalidad_juridica.strip()
		self.numero_registro = self.numero_registro.strip()
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre


class VecinoJunta(models.Model):
	vecino = models.ForeignKey(
		Vecino,
		on_delete=models.PROTECT,
		related_name='juntas_relacionadas',
	)
	junta = models.ForeignKey(
		JuntaVecinos,
		on_delete=models.PROTECT,
		related_name='vecinos_relacionados',
	)
	es_dirigente = models.BooleanField(default=False)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['vecino__nombre', 'junta__nombre', 'pk']
		constraints = [
			models.UniqueConstraint(
				fields=['vecino', 'junta'],
				name='vecino_junta_unica',
			),
		]
		verbose_name = 'relación vecino-junta'
		verbose_name_plural = 'relaciones vecino-junta'


class Territorio(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='territorios_objetivo',
		db_column='DELEGACION',
	)

	class Meta:
		db_table = 'territorio'
		verbose_name = 'territorio'
		verbose_name_plural = 'territorios'

	def __str__(self):
		return self.nombre


class CargoJv(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	permisos = models.CharField(max_length=500, db_column='PERMISOS')
	junta_vecino = models.ForeignKey(
		JuntaVecinos,
		on_delete=models.PROTECT,
		related_name='cargos_objetivo',
		db_column='JUNTA_VECINO',
	)

	class Meta:
		db_table = 'cargo_jv'
		verbose_name = 'cargo de junta de vecinos'
		verbose_name_plural = 'cargos de junta de vecinos'

	def __str__(self):
		return self.nombre


class Beneficiado(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	nombre = models.CharField(max_length=50, db_column='NOMBRE')
	apellido = models.CharField(max_length=50, db_column='APELLIDO')
	telefono = models.CharField(max_length=20, db_column='TELEFONO')
	email = models.EmailField(max_length=90, null=True, blank=True, db_column='EMAIL')

	class Meta:
		db_table = 'beneficiado'
		verbose_name = 'beneficiado'
		verbose_name_plural = 'beneficiados'

	def __str__(self):
		return f'{self.nombre} {self.apellido}'


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
