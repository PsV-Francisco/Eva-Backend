import uuid
import re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalizar_telefono(value):
	return re.sub(r'\D', '', value or '')

#Modelo : Tipo (OK)
class Tipo(models.Model):
	class Estado(models.TextChoices):
		ACTIVADO = 'ACTIVADO', 'Activado'
		DESACTIVADO = 'DESACTIVADO', 'Desactivado'
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVADO)
	
	class Meta:
		ordering = ['-nombre', '-estado']
		db_table = "tipo"
		verbose_name = "Tipo"
		verbose_name_plural = "Tipos"
	
	def __str__(self):
		return f'{self.nombre} - {self.estado}'
	
#Modelo : Subtipo (OK)
class Subtipo(models.Model):
	class Estado(models.TextChoices):
		ACTIVADO = 'ACTIVADO', 'Activado'
		DESACTIVADO = 'DESACTIVADO', 'Desactivado'
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVADO, db_column='ESTADO')
	tipo = models.ForeignKey(Tipo, on_delete=models.PROTECT, db_column='TIPO', related_name='subtipos')
	
	class Meta:
		ordering = ['-nombre', '-estado']
		db_table = "subtipo"
		verbose_name = "subtipo"
		verbose_name_plural = "Subtipos"
	
	def __str__(self):
		return f'{self.nombre} - {self.estado}'

#Modelo : Registro (OK)
class Registro(models.Model):
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		VALIDADA = 'validada', 'Validada'
		OBSERVADA = 'observada', 'Observada'
		ANULADA = 'anulada', 'Anulada'
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False,db_column='CODIGO')
	fecha = models.DateField(db_column='FECHA')
	item = models.ForeignKey('CoordinadorApp.Item',on_delete=models.PROTECT,db_column='ITEM',related_name='registros',)
	periodo = models.ForeignKey('CoordinadorApp.Periodo',on_delete=models.PROTECT,db_column='PERIODO',related_name='registros',)
	descripcion = models.CharField(max_length=240,db_column='DESCRIPCION')
	contacto = models.CharField(max_length=160, blank=True,db_column='CONTACTO')
	telefono = models.IntegerField(blank=True, null=True,db_column='TELEFONO')
	accion = models.TextField(blank=True,db_column='ACCION')
	autor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,db_column='AUTOR',related_name='registros',)
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE,db_column='ESTADO')
	incluir_en_agenda = models.BooleanField(default=False,db_column='INCLUIR_EN_AGENDA')
	creado = models.DateTimeField(auto_now_add=True)
	fecha_cierre = models.DateTimeField(default=timezone.now, db_column='FECHA_CIERRE')
	genera_puntaje = models.CharField(max_length=45, null=True, blank=True, db_column='GENERA_PUNTAJE')
	tipo = models.ForeignKey(Tipo,on_delete=models.PROTECT,db_column='TIPO',related_name='registros')
	subtipo = models.ForeignKey(Subtipo,on_delete=models.PROTECT,db_column='SUBTIPO',related_name='registros')
	evidencia = models.ForeignKey('SupervisorApp.Evidencia',on_delete=models.SET_NULL,db_column='EVIDENCIA',related_name='registros',null=True,blank=True,verbose_name='Evidencia principal')

	class Meta:
		ordering = ['-fecha', '-creado']
		db_table = "registro"
		verbose_name = "Registro"
		verbose_name_plural = "Registros"

	@property
	def evidencias_registros(self):
		"""Retorna un QuerySet vacío de Evidencia dado que el modelo Evidencia no posee relación con Registro."""
		from SupervisorApp.models import Evidencia
		return Evidencia.objects.none()

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

#Modelo Beneficiado
class Beneficiado(models.Model):
	nombre = models.CharField(max_length=50, db_column='NOMBRE')
	apellido = models.CharField(max_length=50, db_column='APELLIDO')
	telefono = models.IntegerField(db_column='TELEFONO')
	email = models.CharField(max_length=90, null=True, blank=True, db_column='EMAIL')

	class Meta:
		ordering = ['nombre']
		db_table = 'beneficiado'
		verbose_name = "beneficiado"
		verbose_name_plural = "Beneficiados"

	def __str__(self):
		return f'{self.nombre} {self.apellido}'

#Modelo : Vecino (OK)
class Vecino(models.Model):
	class Estado(models.TextChoices):
		ACTIVADO = 'ACTIVADO', 'Activado'
		DESACTIVADO = 'DESACTIVADO', 'Desactivado'

	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	telefono = models.CharField(max_length=15, null=True, blank=True, db_column='TELEFONO')
	direccion = models.CharField(max_length=250, null=True, blank=True, db_column='DIRECCION')
	territorio = models.ForeignKey('Territorio',on_delete=models.PROTECT,db_column='TERRITORIO',related_name='vecinos',)
	delegacion = models.ForeignKey('AdminApp.Delegacion',on_delete=models.PROTECT,db_column='DELEGACION',related_name='vecinos',)
	cargo_jv = models.ForeignKey('CargoJV',on_delete=models.PROTECT,db_column='CARGO_JV',related_name='vecinos',)
	junta_vecino = models.ForeignKey('JuntaVecino',on_delete=models.PROTECT,db_column='JUNTA_VECINO',related_name='vecinos',)
	estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVADO, db_column='ESTADO')
	activo = models.BooleanField(default=True)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'vecino'
		ordering = ['nombre']
		indexes = [
			models.Index(fields=['delegacion', 'activo', 'nombre']),
			models.Index(fields=['delegacion', 'telefono']),
		]
		verbose_name = 'vecino'
		verbose_name_plural = 'vecinos'

	def clean(self):
		errors = {}
		self.nombre = self.nombre.strip()
		if len(self.nombre) < 2:
			errors['nombre'] = 'Ingresa un nombre válido.'
		if self.telefono:
			self.telefono = self.telefono.strip()
			phone_digits = normalizar_telefono(self.telefono)
			if not 7 <= len(phone_digits) <= 15:
				errors['telefono'] = 'Ingresa un teléfono válido.'
		if not self.territorio_id:
			errors['territorio'] = 'Ingresa un territorio.'
		if self.territorio_id and self.territorio.delegacion_id != self.delegacion_id:
			errors['territorio'] = 'El territorio debe pertenecer a la misma delegación.'
		if self.cargo_jv_id and self.junta_vecino_id:
			if self.cargo_jv.junta_vecino_id != self.junta_vecino_id:
				errors['cargo_jv'] = 'El cargo debe pertenecer a la junta seleccionada.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		self.nombre = self.nombre.strip()
		if self.telefono:
			self.telefono = self.telefono.strip()
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre

#Modelo : Territorio (OK)
class Territorio(models.Model):
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	delegacion = models.ForeignKey('AdminApp.Delegacion',on_delete=models.PROTECT,db_column='DELEGACION',related_name='territorios',)

	class Meta:
		db_table = 'territorio'
		ordering = ['nombre']
		verbose_name = 'territorio'
		verbose_name_plural = 'territorios'

	def __str__(self):
		return self.nombre

#Modelo : JuntaVecino (OK)
class JuntaVecino(models.Model):
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	domicilio_legal = models.CharField(max_length=100, db_column='DOMICILIO_LEGAL')
	socios_activos = models.IntegerField(null=True, blank=True, db_column='SOCIOS_ACTIVOS')
	fecha_constitucion = models.DateTimeField(null=True, blank=True, db_column='FECHA_CONSTITUCION',)
	numero_rpj = models.IntegerField(db_column='NUMERO_RPJ')
	fecha_ingreso = models.DateTimeField(null=True, blank=True, db_column='FECHA_INGRESO')
	numero_registro = models.IntegerField(null=True, blank=True, db_column='NUMERO_REGISTRO')
	territorio = models.ForeignKey(Territorio,on_delete=models.PROTECT,db_column='TERRITORIO',related_name='juntas_vecinos',)
	delegacion = models.ForeignKey('AdminApp.Delegacion',on_delete=models.PROTECT,db_column='DELEGACION',related_name='juntas_vecinos',)
	creado = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = 'junta_vecino'
		ordering = ['nombre']
		indexes = [
			models.Index(fields=['delegacion','nombre']),
			models.Index(fields=['numero_rpj']),
		]
		verbose_name = 'junta de vecinos'
		verbose_name_plural = 'juntas de vecinos'

	def clean(self):
		errors = {}
		self.nombre = self.nombre.strip()
		self.domicilio_legal = self.domicilio_legal.strip()
		if len(self.nombre) < 2:
			errors['nombre'] = 'Ingresa un nombre válido.'
		if self.socios_activos is not None and self.socios_activos < 0:
			errors['socios_activos'] = 'La cantidad no puede ser negativa.'
		if self.territorio_id and self.territorio.delegacion_id != self.delegacion_id:
			errors['territorio'] = 'El territorio debe pertenecer a la misma delegación.'
		if (
			self.fecha_ingreso
			and self.fecha_constitucion
			and self.fecha_ingreso < self.fecha_constitucion
		):
			errors['fecha_ingreso'] = 'La fecha de ingreso no puede ser anterior a la constitución.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		self.nombre = self.nombre.strip()
		self.domicilio_legal = self.domicilio_legal.strip()
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre

#Modelo : CargoJv (OK)
class CargoJv(models.Model):
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	permisos = models.CharField(max_length=500, db_column='PERMISOS')
	junta_vecino = models.ForeignKey(JuntaVecino,on_delete=models.PROTECT,db_column='JUNTA_VECINO',related_name='cargos',)

	class Meta:
		db_table = 'cargo_jv'
		ordering = ['nombre']
		verbose_name = 'cargo de junta de vecinos'
		verbose_name_plural = 'cargos de junta de vecinos'

	def __str__(self):
		return self.nombre


def tipo_subtipo_predeterminados(tipo=None):
	if tipo is None:
		tipo, _ = Tipo.objects.get_or_create(
			nombre='Sin tipo',
			defaults={'estado': Tipo.Estado.ACTIVADO},
		)
	subtipo, _ = Subtipo.objects.get_or_create(
		nombre='Sin subtipo',
		tipo=tipo,
		defaults={'estado': Subtipo.Estado.ACTIVADO},
	)
	return tipo, subtipo