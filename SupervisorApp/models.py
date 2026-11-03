import uuid
from pathlib import Path
from typing import Optional
from django.conf import settings
from django.db import models
from DelegadoApp.models import Compromiso
from CoordinadorApp.models import GestionAtencion
from FuncionarioApp.models import Registro
#from SupervisorApp.files import validate_evidence_file


def evidence_upload_path(instance, filename):
	extension = Path(filename).suffix.lower()
	return f'evidencias/{uuid.uuid4().hex}{extension}'


#Modelo : Evidencia (OK)
class Evidencia(models.Model):
	#Creación de la clase Estado para tener un seleccionable en el atributo estado.
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	archivo = models.FileField(upload_to=evidence_upload_path)
	tipo_archivo = models.CharField(max_length=50, blank=True, db_column='TIPO_ARCHIVO')
	fecha = models.DateTimeField(auto_now_add=True)
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
	#FK del Registro
	registro = models.ForeignKey('FuncionarioApp.Registro', on_delete=models.CASCADE, related_name='evidencias_registros', null=True, blank=True)
	autor_registro = models.IntegerField(null=True, blank=True, db_column='AUTOR_REGISTRO')
	item_registro = models.IntegerField(null=True, blank=True, db_column='ITEM_REGISTRO')
	periodo_registro = models.IntegerField(null=True, blank=True, db_column='PERIODO_REGISTRO')
	#FK del Compromiso
	compromiso = models.ForeignKey('DelegadoApp.Compromiso',on_delete=models.CASCADE, related_name='evidencias_compromiso', null=True, blank=True)
	gestion_atencion = models.ForeignKey(
		'CoordinadorApp.GestionAtencion',
		on_delete=models.CASCADE,
		related_name='evidencias',
		null=True,
		blank=True,
	)
	responsable_compromiso = models.IntegerField(null=True, blank=True, db_column='RESPONSABLE_COMPROMISO',)
	agenda_compromiso = models.IntegerField(null=True, blank=True, db_column='AGENDA_COMPROMISO')
	agenda_periodo_compromiso = models.IntegerField(null=True, blank=True, db_column='AGENDA_PERIODO_COMPROMISO',)
	agenda_delegacion_compromiso = models.IntegerField(null=True, blank=True, db_column='AGENDA_DELEGACION_COMPROMISO',)
	supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,related_name='evidencias_supervisor', null=True, blank=True,)
	autor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,db_column='AUTOR',related_name='evidencias_autor',null=True,blank=True,)

	class Meta:
		ordering = ['-fecha']
		db_table = "evidencia"
		verbose_name = 'Evidencia'
		verbose_name_plural = 'Evidencias'
		constraints = [models.CheckConstraint(condition=(
			models.Q(registro__isnull=False, compromiso__isnull=True, gestion_atencion__isnull=True)
			| models.Q(registro__isnull=True, compromiso__isnull=False, gestion_atencion__isnull=True)
			| models.Q(registro__isnull=True, compromiso__isnull=True, gestion_atencion__isnull=False)),
            name='evidencia_asociada_a_un_solo_origen')]

	def __str__(self):
		return f'Evidencia {self.codigo} ({self.get_estado_display()})'

	# def clean(self):
		# if self.archivo and not self.archivo._committed:
			# validate_evidence_file(self.archivo.file)

	def asignarEvidencia(
		self,
		registro: Optional[Registro] = None,
		compromiso: Optional[Compromiso] = None,
		gestion_atencion: Optional[GestionAtencion] = None,
	) -> None:
		"""Asigna esta evidencia a un único registro, compromiso o atención."""
		targets = (registro, compromiso, gestion_atencion)
		if sum(target is not None for target in targets) != 1:
			raise ValueError('Indica exactamente un registro, compromiso o atención.')
		self.registro = registro
		self.compromiso = compromiso
		self.gestion_atencion = gestion_atencion

	def save(self, *args, **kwargs):
		if self.pk:
			original_code = type(self).objects.filter(pk=self.pk).values_list(
				'codigo', flat=True,
			).first()
			if original_code and original_code != self.codigo:
				raise ValueError('El código de evidencia es inmutable.')
		return super().save(*args, **kwargs)
	

#Modelo : RevisionEvidencia (OK)
class RevisionEvidencia(models.Model):
	class Decision(models.TextChoices):
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		CORRECCION = 'correccion', 'Solicitar corrección'

	verificador = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='revisiones_evidencia',)
	decision = models.CharField(max_length=100, choices=Decision.choices, db_column='DECISION',)
	observaciones = models.CharField(max_length=200, blank=True, db_column='OBSERVACIONES',)
	fecha = models.DateTimeField(auto_now_add=True)
	#FK de Evidencia
	evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name='revisiones')
	autor_evidencia = models.IntegerField(null=True, blank=True, db_column='AUTOR_EVIDENCIA')
	#FK del registro en la evidencia
	registro_evidencia = models.IntegerField(null=True, blank=True, db_column='REGISTRO_EVIDENCIA',)
	registro_autor_evidencia = models.IntegerField(null=True, blank=True, db_column='REGISTRO_AUTOR_EVIDENCIA',)
	registro_item_evidencia = models.IntegerField(null=True, blank=True, db_column='REGISTRO_ITEM_EVIDENCIA',)
	registro_periodo_evidencia = models.IntegerField(null=True, blank=True, db_column='REGISTRO_PERIODO_EVIDENCIA',)
	#FK del Compromiso en la Evidencia
	compromiso_evidencia = models.IntegerField(null=True, blank=True, db_column='COMPROMISO_EVIDENCIA',)
	compromiso_responsable_evidencia = models.IntegerField(null=True, blank=True, db_column='COMPROMISO_RESPONSABLE_EVIDENCIA',)
	compromiso_agenda_evidencia = models.IntegerField(null=True, blank=True, db_column='COMPROMISO_AGENDA_EVIDENCIA',)
	compromiso_periodo_agenda_evidencia = models.IntegerField(null=True, blank=True, db_column='COMPROMISO_PERIODO_AGENDA_EVIDENCIA',)
	compromiso_delegacion_agenda_evidencia = models.IntegerField(null=True, blank=True, db_column='COMPROMISO_DELEGACION_AGENDA_EVIDENCIA',)

	class Meta:
		ordering = ['-fecha']
		db_table = "revision_evidencia"
		verbose_name = 'revision_evidencia'
		verbose_name_plural = 'revision_evidencias'

	def __str__(self):
		return f'{self.get_decision_display()} - {self.evidencia.codigo}'
