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
	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False,db_column='CODIGO')
	archivo = models.FileField(upload_to=evidence_upload_path,db_column='ARCHIVO')
	tipo_archivo = models.CharField(max_length=50, blank=True, db_column='TIPO_ARCHIVO')
	fecha = models.DateTimeField(auto_now_add=True,db_column="FECHA")
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE,db_column='ESTADO')

	class Meta:
		ordering = ['-fecha']
		db_table = "evidencia"
		verbose_name = 'Evidencia'
		verbose_name_plural = 'Evidencias'

	def __str__(self):
		return f'Evidencia {self.codigo} ({self.get_estado_display()})'

	

#Modelo : RevisionEvidencia (OK)
class RevisionEvidencia(models.Model):
	class Decision(models.TextChoices):
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		CORRECCION = 'correccion', 'Solicitar corrección'

	verificador = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='revisiones_evidencia',db_column='VERIFICADOR')
	decision = models.CharField(max_length=100, choices=Decision.choices, db_column='DECISION',)
	observaciones = models.CharField(max_length=200, blank=True, db_column='OBSERVACIONES',)
	fecha = models.DateTimeField(auto_now_add=True,db_column='FECHA')
	#FK de Evidencia
	evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name='revisiones',db_column='EVIDENCIA')
	autor_evidencia = models.IntegerField(null=True, blank=True, db_column='AUTOR_EVIDENCIA')

	class Meta:
		ordering = ['-fecha']
		db_table = "revision_evidencia"
		verbose_name = 'revision_evidencia'
		verbose_name_plural = 'revision_evidencias'

	def __str__(self):
		return f'{self.get_decision_display()} - {self.evidencia.codigo}'
