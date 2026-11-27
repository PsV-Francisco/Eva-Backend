import secrets
import string
from django.conf import settings
from django.db import models

from django.core.exceptions import ValidationError
from django.utils import timezone


# Validación auxiliar para no alterar períodos cerrados (HU-04)
def _validar_fecha_no_en_periodo_cerrado(fecha, field_name='vigente_desde'):
	if not fecha:
		return
	periodo_cerrado = Periodo.objects.filter(
		estado=Periodo.Estado.CERRADO,
		fecha_inicio__lte=fecha,
		fecha_fin__gte=fecha,
	).first()
	if periodo_cerrado:
		raise ValidationError({
			field_name: (
				f'La fecha {fecha:%d/%m/%Y} pertenece al período cerrado '
				f'"{periodo_cerrado.nombre}" y no puede modificarse.'
			)
		})


#Modelo : Funcion (OK)
class Funcion(models.Model):
	class Estado(models.TextChoices):
		ACTIVO = 'activo', 'Activo'
		INACTIVO = 'inactivo', 'Inactivo'

	nombre = models.CharField(max_length=120, unique=True)
	descripcion = models.TextField(blank=True)
	estado = models.CharField(
		max_length=20,
		choices=Estado.choices,
		default=Estado.ACTIVO,
	)

	class Meta:
		ordering = ['nombre']
		db_table = "funcion"
		verbose_name = 'función'
		verbose_name_plural = 'funciones'

	def __str__(self):
		return self.nombre

#Modelo : Item (OK)
class Item(models.Model):
	class Estado(models.TextChoices):
		ACTIVO = 'activo', 'Activo'
		INACTIVO = 'inactivo', 'Inactivo'

	codigo = models.CharField(max_length=20, unique=True, null=True)
	nombre = models.CharField(max_length=120)
	descripcion = models.TextField(blank=True)
	
	estado = models.CharField(max_length=20,choices=Estado.choices,default=Estado.ACTIVO,)

	class Meta:
		ordering = ['nombre']
		db_table = "item"
		verbose_name = 'Item'
		verbose_name_plural = 'Items'

	def __str__(self):
		return self.nombre

	def save(self, *args, **kwargs):
		if not self.codigo and self.pk is None:
			super().save(*args, **kwargs)
			self.codigo = f'ITEM-{self.pk:04d}'
			super().save(using=kwargs.get('using'), update_fields=['codigo'])
			return
		return super().save(*args, **kwargs)


#Modelo : CargoFuncion (OK)
class CargoFuncion(models.Model):
	cargo = models.ForeignKey('AdminApp.Cargo', on_delete=models.PROTECT, related_name='asignaciones_funciones')
	funcion = models.ForeignKey(Funcion, on_delete=models.PROTECT, related_name='asignaciones_cargos')
	vigente_desde = models.DateField(default=timezone.localdate, db_column='VIGENTE_DESDE')
	vigente_hasta = models.DateField(null=True, blank=True, db_column='VIGENTE_HASTA')

	class Meta:
		ordering = ['cargo', '-vigente_desde']
		db_table = "cargo_funcion"
		verbose_name = 'CargoFuncion'
		verbose_name_plural = 'Funciones por cargo'
		# Cambio HU-04: Restricción única solo para asignaciones vigentes, permitiendo conservar historial cerrado
		constraints = [
			models.UniqueConstraint(
				fields=['cargo', 'funcion'],
				condition=models.Q(vigente_hasta__isnull=True),
				name='cargo_funcion_vigente_unica',
			),
		]

	def clean(self):
		super().clean()
		if self.vigente_hasta and self.vigente_desde and self.vigente_hasta < self.vigente_desde:
			raise ValidationError({'vigente_hasta': 'La fecha de término debe ser igual o posterior al inicio de vigencia.'})
		if self.pk:
			anterior = type(self).objects.filter(pk=self.pk).first()
			if anterior and anterior.vigente_desde != self.vigente_desde:
				_validar_fecha_no_en_periodo_cerrado(anterior.vigente_desde, 'vigente_desde')
		_validar_fecha_no_en_periodo_cerrado(self.vigente_desde, 'vigente_desde')
		if self.vigente_hasta:
			_validar_fecha_no_en_periodo_cerrado(self.vigente_hasta, 'vigente_hasta')

	def __str__(self):
		return f'{self.cargo} - {self.funcion}'


#Modelo : CargoItem (HU-04: Ítems de medición vigentes asociados a cada cargo)
class CargoItem(models.Model):
	cargo = models.ForeignKey('AdminApp.Cargo', on_delete=models.PROTECT, related_name='asignaciones_items')
	item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='asignaciones_cargos')
	vigente_desde = models.DateField(default=timezone.localdate, db_column='VIGENTE_DESDE')
	vigente_hasta = models.DateField(null=True, blank=True, db_column='VIGENTE_HASTA')

	class Meta:
		ordering = ['cargo', '-vigente_desde']
		db_table = 'cargo_item'
		verbose_name = 'Ítem por cargo'
		verbose_name_plural = 'Ítems por cargo'
		constraints = [
			models.UniqueConstraint(
				fields=['cargo', 'item'],
				condition=models.Q(vigente_hasta__isnull=True),
				name='cargo_item_vigente_unico',
			),
		]

	def clean(self):
		super().clean()
		if self.vigente_hasta and self.vigente_desde and self.vigente_hasta < self.vigente_desde:
			raise ValidationError({'vigente_hasta': 'La fecha de término debe ser igual o posterior al inicio de vigencia.'})
		if self.pk:
			anterior = type(self).objects.filter(pk=self.pk).first()
			if anterior and anterior.vigente_desde != self.vigente_desde:
				_validar_fecha_no_en_periodo_cerrado(anterior.vigente_desde, 'vigente_desde')
		_validar_fecha_no_en_periodo_cerrado(self.vigente_desde, 'vigente_desde')
		if self.vigente_hasta:
			_validar_fecha_no_en_periodo_cerrado(self.vigente_hasta, 'vigente_hasta')

	def __str__(self):
		return f'{self.cargo} - {self.item}'


#Modelo : Periodo (OK)
class Periodo(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'abierto', 'Abierto'
		CERRADO = 'cerrado', 'Cerrado'

	nombre = models.CharField(max_length=120, unique=True)
	fecha_inicio = models.DateField()
	fecha_fin = models.DateField()
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)
	# Snapshot de las reglas que regían al cerrar el período.
	semaforo_rojo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	semaforo_ambar = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	umbral_delegacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	tope_cumplimiento = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

	class Meta:
		ordering = ['-fecha_inicio']
		db_table = "periodo"
		verbose_name = 'Periodo'
		verbose_name_plural = 'Periodos'
		constraints = [
			models.CheckConstraint(
				condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')),
				name='periodo_fecha_fin_despues_inicio',
			),
		]

	def save(self, *args, **kwargs):
		# HU-28: guarda siempre el estado en minúsculas ('Abierto' -> 'abierto').
		# MariaDB compara sin distinguir mayúsculas, pero el código Python sí.
		self.estado = (self.estado or '').strip().lower() or self.Estado.ABIERTO
		if self.estado == self.Estado.CERRADO and any(
			getattr(self, field, None) is None
			for field in ('semaforo_rojo', 'semaforo_ambar', 'umbral_delegacion', 'tope_cumplimiento')
		):
			from AdminApp.models import ParametroSistema
			self.semaforo_rojo = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_ROJO)
			self.semaforo_ambar = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_AMBAR)
			self.umbral_delegacion = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION)
			self.tope_cumplimiento = ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO)
		return super().save(*args, **kwargs)

	def __str__(self):
		return self.nombre


class SolicitudAutorizacionPeriodo(models.Model):
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		CANCELADA = 'cancelada', 'Cancelada'
		REVOCADA = 'revocada', 'Revocada'
		VENCIDA = 'vencida', 'Vencida'

	periodo = models.ForeignKey(
		Periodo,
		on_delete=models.PROTECT,
		related_name='solicitudes_autorizacion',
	)
	vecino = models.ForeignKey(
        'FuncionarioApp.Vecino', 
        on_delete=models.PROTECT, 
        related_name='vecino_solicitud_autorizacion_periodo', 
        null=True, 
        blank=True, 
        verbose_name='Vecino', 
        db_column='VECINO'
    )
	aprobador = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='autorizaciones_periodo_resueltas',
	)
	funcionarios = models.ManyToManyField(
		settings.AUTH_USER_MODEL,
		related_name='autorizaciones_periodo_funcionario',
	)
	alcances = models.JSONField(default=list)
	motivo = models.TextField()
	comentario_aprobador = models.TextField(blank=True)
	estado = models.CharField(
		max_length=16,
		choices=Estado.choices,
		default=Estado.PENDIENTE,
	)
	creada_en = models.DateTimeField(auto_now_add=True)
	decidida_en = models.DateTimeField(null=True, blank=True)
	vence_en = models.DateTimeField(null=True, blank=True)
	usada_en = models.DateTimeField(null=True, blank=True)
	revocada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		db_table = 'solicitud_autorizacion_periodo'
		ordering = ['-creada_en']

	def __str__(self):
		return f'Autorización de {self.periodo} solicitada por {self.vecino}'


#Modelo : PeriodoSemana (OK)
class PeriodoSemana(models.Model):
	class Estado(models.TextChoices):
		ABIERTO = 'abierto','Abierto'
		CERRADO = 'cerrado','Cerrado'

	nombre = models.CharField(max_length=100, db_column='NOMBRE')
	fecha_inicio = models.DateTimeField(null=True, blank=True, db_column='FECHA_INICIO')
	fecha_fin = models.DateTimeField(null=True, blank=True, db_column='FECHA_FIN')
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTO)
	periodo = models.ForeignKey('Periodo', on_delete=models.PROTECT, db_column='PERIODO')

	class Meta:
		db_table = 'periodo_semana'
		ordering = ['-fecha_inicio']
		verbose_name = "Semana del Periodo"
		verbose_name_plural = "Semanas del Periodo"

#Modelo : Desempeño (OK)
class Desempeno(models.Model):
	
	usuario = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='desempenos',)
	item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='desempenos')
	ponderacion = models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True,db_column='PONDERACION',)
	meta = models.DecimalField(max_digits=12, decimal_places=2)
	avance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	ultimo_registro = models.DateField(null=True, blank=True)
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='desempenos')

	class Meta:
		ordering = ['periodo', 'usuario', 'item']
		db_table = "desempeño"
		verbose_name = 'Desempeño'
		verbose_name_plural = 'Desempeños'
		constraints = [
			models.UniqueConstraint(
				fields=['usuario', 'item', 'periodo'],
				name='desempeno_unico_por_usuario_item_periodo',
			),
			models.CheckConstraint(condition=models.Q(meta__gt=0), name='desempeno_meta_positiva'),
			models.CheckConstraint(condition=models.Q(avance__gte=0), name='desempeno_avance_no_negativo'),
		]

	def __str__(self):
		return f'{self.usuario} - {self.item} - {self.periodo}'

	def save(self, *args, **kwargs):
		if self.pk and self.periodo_id:
			estado_periodo = Periodo.objects.filter(pk=self.periodo_id).values_list('estado', flat=True).first()
			if estado_periodo == Periodo.Estado.CERRADO:
				raise ValidationError('No se puede modificar ni recalcular el desempeño de un período cerrado.')
		return super().save(*args, **kwargs)


#Modelo : GestionAtencion (OK)

class GestionAtencion(models.Model):
    codigo = models.CharField(max_length=20, unique=True, editable=False)
    fecha = models.DateField(db_column='FECHA')
    observaciones = models.TextField(blank=True, db_column='OBSERVACIONES')
    nombre = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        ordering = ['-fecha']
        db_table = 'gestion_atencion'
        verbose_name = 'gestión de atención'
        verbose_name_plural = 'gestiones de atenciones'

    def __str__(self):
        if self.nombre:
            return f'{self.nombre} ({self.codigo}) - {self.fecha:%Y-%m-%d}'
        return f'Gestión {self.codigo} - {self.fecha:%Y-%m-%d}'

    @classmethod
    def generar_codigo_unico(cls):
        caracteres = string.ascii_uppercase + string.digits
        while True:
            codigo = ''.join(secrets.choice(caracteres) for _ in range(20))
            if not cls.objects.filter(codigo=codigo).exists():
                return codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self.generar_codigo_unico()
        elif self.pk:
            original_code = type(self).objects.filter(pk=self.pk).values_list('codigo', flat=True).first()
            if original_code and original_code != self.codigo:
                raise ValueError('El código de atención es inmutable.')
        return super().save(*args, **kwargs)

    @property
    def cantidad_atenciones(self):
        return self.atencionsocial_set.count()

    @property
    def tiempos_etapas(self):
        """Calcula los días transcurridos entre Etapa 1->2, Etapa 2->3 y total."""
        etapas = {a.etapa: a.fecha for a in self.atencionsocial_set.all()}
        e1, e2, e3 = etapas.get(1), etapas.get(2), etapas.get(3)
        d_1_2 = (e2.date() - e1.date()).days if (e1 and e2) else None
        d_2_3 = (e3.date() - e2.date()).days if (e2 and e3) else None
        fechas = sorted(etapas.values())
        d_total = (fechas[-1].date() - fechas[0].date()).days if len(fechas) >= 2 else None
        return {
            'etapa_1_a_2': d_1_2,
            'etapa_2_a_3': d_2_3,
            'total_dias': d_total,
        }


#Modelo : AtencionSocial (OK)
class AtencionSocial(models.Model):
	class Etapa(models.IntegerChoices):
		VISITA_PROGRAMADA = 1, 'Etapa 1: Visita programada'
		VISITA_INFORME = 2, 'Etapa 2: Visita / Informe'
		ENTREGA_BENEFICIO = 3, 'Etapa 3: Entrega de beneficio'

	etapa = models.PositiveSmallIntegerField(choices=Etapa.choices,default=Etapa.VISITA_PROGRAMADA,db_column='ETAPA',)
	fecha = models.DateTimeField(db_column='FECHA')
	resultado = models.TextField(blank=True, db_column='RESULTADO')
	observaciones = models.TextField(blank=True, db_column="OBSERVACIONES")
	autor = models.ForeignKey('AdminApp.Usuario', on_delete=models.PROTECT, db_column='AUTOR')
	vecino = models.ForeignKey('FuncionarioApp.Vecino', on_delete=models.PROTECT, related_name='atenciones_sociales', null=True, blank=True, verbose_name='Vecino', db_column='VECINO')
	tipo = models.ForeignKey('FuncionarioApp.Tipo', on_delete=models.PROTECT, db_column='TIPO', related_name='Atencion_Social')
	subtipo = models.ForeignKey('FuncionarioApp.Subtipo', on_delete=models.PROTECT, db_column='SUBTIPO', related_name='Atencion_Social')
	gestion_atencion = models.ForeignKey(GestionAtencion, on_delete=models.PROTECT, db_column='GESTION_ATENCION')
	evidencia = models.ForeignKey('SupervisorApp.Evidencia', on_delete=models.PROTECT, null=True, blank=True, db_column='EVIDENCIA', related_name='atenciones_sociales')
	creado = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['gestion_atencion', 'etapa', '-fecha']
		db_table = 'atencion_social'
		verbose_name = 'atención social'
		verbose_name_plural = 'atenciones sociales'

	@property
	def dias_desde_etapa_anterior(self):
		if self.etapa <= 1 or not self.gestion_atencion_id or not self.fecha:
			return None
		anterior = AtencionSocial.objects.filter(
			gestion_atencion_id=self.gestion_atencion_id,
			etapa=self.etapa - 1,
		).first()
		if anterior and anterior.fecha:
			return max((self.fecha.date() - anterior.fecha.date()).days, 0)
		return None

	def __str__(self):
		return f'Atención {self.pk} ({self.get_etapa_display()}) - {self.tipo}'
