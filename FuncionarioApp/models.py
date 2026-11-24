import uuid
import re
from datetime import datetime, time, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


MAX_ACTIVIDADES_DIARIAS = 7
WEEKLY_CLOSURE_MESSAGE = 'El período semanal está cerrado'


def normalizar_telefono(value):
	return re.sub(r'\D', '', value or '')


def limite_diario_actividades(user):
	"""Retorna el tope diario de actividades para el funcionario (por defecto 7)."""
	custom_limit = getattr(user, 'limite_actividad', 0) or 0
	return custom_limit if custom_limit > 0 else MAX_ACTIVIDADES_DIARIAS


def fecha_cierre_semanal(fecha, now=None):
	"""Return the local Monday 23:59:59.999999 deadline for an activity date."""
	if not fecha:
		return None
	fecha = fecha.date() if isinstance(fecha, datetime) else fecha
	lunes = fecha - timedelta(days=fecha.weekday())
	lunes_siguiente = lunes + timedelta(days=7)
	deadline = datetime.combine(lunes_siguiente, time.max)
	return timezone.make_aware(deadline, timezone.get_current_timezone())


def periodo_semanal_abierto(fecha, now=None):
	if not fecha:
		return True
	actual = timezone.localtime(now or timezone.now())
	return actual <= fecha_cierre_semanal(fecha, actual)


def validar_periodo_semanal_abierto(fecha, now=None):
	if not periodo_semanal_abierto(fecha, now):
		raise ValidationError(WEEKLY_CLOSURE_MESSAGE)


def validar_y_normalizar_rut(rut_input):
	"""Valida formato y dígito verificador Módulo 11. Retorna RUT limpio '12345678-9'."""
	rut_limpio = (rut_input or '').strip().replace('.', '').replace(' ', '').upper()
	if not rut_limpio:
		raise ValidationError('El RUT es obligatorio.')
	if not re.match(r'^\d{7,8}-[\dK]$', rut_limpio):
		raise ValidationError('Formato de RUT inválido. Usa el formato 12345678-9.')

	cuerpo, dv = rut_limpio.split('-')
	suma = 0
	multiplo = 2
	for r in reversed(cuerpo):
		suma += int(r) * multiplo
		multiplo = 2 if multiplo == 7 else multiplo + 1
	esperado = 11 - (suma % 11)
	dv_calculado = 'K' if esperado == 10 else ('0' if esperado == 11 else str(esperado))
	if dv_calculado != dv:
		raise ValidationError('El dígito verificador del RUT no es válido.')
	return rut_limpio


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
	periodo = models.ForeignKey('CoordinadorApp.Periodo',on_delete=models.PROTECT,db_column='PERIODO',related_name='registros')
	descripcion = models.CharField(max_length=240,db_column='DESCRIPCION')
	vecino = models.ForeignKey('Vecino',on_delete=models.SET_NULL,null=True,blank=True,db_column='VECINO',related_name='registros')
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
		from SupervisorApp.models import Evidencia
		if self.evidencia_id:
			return Evidencia.objects.filter(pk=self.evidencia_id)
		return Evidencia.objects.none()

	def __str__(self):
		return f'{self.codigo} - {self.descripcion}'

	def clean(self):
		super().clean()
		validar_periodo_semanal_abierto(self.fecha)
		if self.autor_id and self.fecha and self.estado != self.Estado.ANULADA:
			limite = limite_diario_actividades(self.autor)
			existentes = (
				type(self)
				.objects.filter(autor_id=self.autor_id, fecha=self.fecha)
				.exclude(estado=self.Estado.ANULADA)
				.exclude(pk=self.pk)
				.count()
			)
			if existentes >= limite:
				raise ValidationError({
					'fecha': f'Has alcanzado el tope máximo de {limite} actividades registradas para el {self.fecha:%d/%m/%Y}.',
				})

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de registro es inmutable.')
		if not self.genera_puntaje:
			self.genera_puntaje = 'SI'
		return super().save(*args, **kwargs)


#Modelo : Vecino (OK)
class Vecino(models.Model):
	class Estado(models.TextChoices):
		ACTIVADO = 'ACTIVADO', 'Activado'
		DESACTIVADO = 'DESACTIVADO', 'Desactivado'

	rut = models.CharField(max_length=12, null=True, blank=True, db_column='RUT')
	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	apellido = models.CharField(max_length=50, null=True, blank=True, db_column='APELLIDO')
	telefono = models.CharField(max_length=15, null=True, blank=True, db_column='TELEFONO')
	email = models.CharField(max_length=90, null=True, blank=True, db_column='EMAIL')
	direccion = models.CharField(max_length=250, null=True, blank=True, db_column='DIRECCION')
	territorio = models.ForeignKey('Territorio', on_delete=models.PROTECT, db_column='TERRITORIO', related_name='vecinos')
	delegacion = models.ForeignKey('AdminApp.Delegacion', on_delete=models.PROTECT, db_column='DELEGACION', related_name='vecinos')
	junta_vecino = models.ForeignKey('JuntaVecino', on_delete=models.PROTECT, db_column='JUNTA_VECINO', related_name='vecinos')
	estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVADO, db_column='ESTADO')
	activo = models.BooleanField(default=True)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'vecino'
		ordering = ['nombre']
		verbose_name = 'vecino'
		verbose_name_plural = 'vecinos'

	@property
	def cargo_actual(self):
		return self.cargos_ejercidos.select_related('junta_vecino').first()

	@property
	def es_dirigente(self):
		return self.cargos_ejercidos.exists()

	def clean(self):
		errors = {}
		self.nombre = (self.nombre or '').strip()
		if len(self.nombre) < 2:
			errors['nombre'] = 'Ingresa un nombre válido.'
		if self.rut:
			try:
				self.rut = validar_y_normalizar_rut(self.rut)
				duplicado = Vecino.objects.filter(rut__iexact=self.rut).exclude(pk=self.pk).exists()
				if duplicado:
					errors['rut'] = f'Ya existe un vecino registrado con el RUT {self.rut}.'
			except ValidationError as exc:
				errors['rut'] = exc.messages[0]
		if self.telefono:
			self.telefono = self.telefono.strip()
			phone_digits = normalizar_telefono(self.telefono)
			if not 7 <= len(phone_digits) <= 15:
				errors['telefono'] = 'Ingresa un teléfono válido.'
		if not self.territorio_id:
			errors['territorio'] = 'Ingresa un territorio.'
		if self.territorio_id and self.territorio.delegacion_id != self.delegacion_id:
			errors['territorio'] = 'El territorio debe pertenecer a la misma delegación.'
		if self.junta_vecino_id and self.junta_vecino.delegacion_id != self.delegacion_id:
			errors['junta_vecino'] = 'La junta de vecinos debe pertenecer a la misma delegación.'
		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		self.nombre = (self.nombre or '').strip()
		if self.rut:
			self.rut = validar_y_normalizar_rut(self.rut)
			if Vecino.objects.filter(rut__iexact=self.rut).exclude(pk=self.pk).exists():
				raise ValidationError({'rut': f'Ya existe un vecino registrado con el RUT {self.rut}.'})
		if self.telefono:
			self.telefono = self.telefono.strip()
		self.activo = (self.estado == self.Estado.ACTIVADO)
		return super().save(*args, **kwargs)

	def __str__(self):
		rut_str = f' ({self.rut})' if self.rut else ''
		return f'{self.nombre}{rut_str}'

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
	junta_vecino = models.ForeignKey(JuntaVecino, on_delete=models.PROTECT, db_column='JUNTA_VECINO', related_name='cargos')
	vecino = models.ForeignKey(Vecino, on_delete=models.SET_NULL, null=True, blank=True, db_column='VECINO', related_name='cargos_ejercidos')

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


# Modelo: Carta (HU-38: Tubo de Cartas y Correspondencia Formal)
class Carta(models.Model):
	class Estado(models.TextChoices):
		INGRESADA = 'INGRESADA', 'Ingresada'
		DERIVADA = 'DERIVADA', 'Derivada'
		EN_PROCESO = 'EN_PROCESO', 'En proceso'
		APROBADA = 'APROBADA', 'Aprobada'
		FINALIZADA = 'FINALIZADA', 'Finalizada'
		NO_APLICA = 'NO_APLICA', 'No aplica'

	numero_carta = models.CharField(max_length=80, db_column='NUMERO_CARTA')
	fecha = models.DateField(db_column='FECHA')
	remitente = models.CharField(max_length=160, db_column='REMITENTE')
	destinatario = models.CharField(max_length=160, db_column='DESTINATARIO')
	telefono = models.CharField(max_length=20, blank=True, null=True, db_column='TELEFONO')
	materia = models.CharField(max_length=255, db_column='MATERIA')
	fecha_respuesta = models.DateField(blank=True, null=True, db_column='FECHA_RESPUESTA')
	responsable_seguimiento = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='cartas_asignadas',
		db_column='RESPONSABLE_SEGUIMIENTO',
	)
	area_derivada = models.CharField(max_length=160, blank=True, db_column='AREA_DERIVADA')
	pronunciamiento = models.TextField(blank=True, db_column='PRONUNCIAMIENTO')
	observaciones = models.TextField(blank=True, db_column='OBSERVACIONES')
	documento_adjunto = models.ForeignKey(
		'SupervisorApp.Evidencia',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='cartas',
		db_column='DOCUMENTO_ADJUNTO',
	)
	fecha_cierre = models.DateField(blank=True, null=True, db_column='FECHA_CIERRE')
	estado = models.CharField(
		max_length=20,
		choices=Estado.choices,
		default=Estado.INGRESADA,
		db_column='ESTADO',
	)
	delegacion = models.ForeignKey(
		'AdminApp.Delegacion',
		on_delete=models.PROTECT,
		related_name='cartas',
		db_column='DELEGACION',
	)
	autor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='cartas_creadas',
		db_column='AUTOR',
	)
	creado = models.DateTimeField(auto_now_add=True)
	actualizado = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'carta'
		ordering = ['-fecha', '-creado']
		indexes = [
			models.Index(fields=['delegacion', 'estado', 'fecha']),
			models.Index(fields=['numero_carta']),
		]
		verbose_name = 'carta'
		verbose_name_plural = 'cartas'

	def __str__(self):
		return f'{self.numero_carta} - {self.materia}'
