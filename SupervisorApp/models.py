import uuid
from typing import Optional

from django.conf import settings
from django.db import models
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import Registro

#Modelo Evidencia
class Evidencia(models.Model):
	#Creación de la clase Estado para tener un seleccionable en el atributo estado.
	class Estado(models.TextChoices):
		PENDIENTE = 'pendiente', 'Pendiente'
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'

	codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	archivo = models.FileField(upload_to='evidencias/')
	registro = models.ForeignKey('FuncionarioApp.Registro', on_delete=models.CASCADE, related_name='evidencias_registros', null=True, blank=True)
	compromiso = models.ForeignKey('DelegadoApp.Compromiso',on_delete=models.CASCADE, related_name='evidencias_compromiso', null=True, blank=True)
	supervisor = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
		related_name='evidencias_supervisor', null=True, blank=True,
	)
	fecha = models.DateTimeField(auto_now_add=True)
	estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)

	class Meta:
		ordering = ['-fecha']
		db_table = "evidencia"
		verbose_name = 'Evidencia'
		verbose_name_plural = 'Evidencias'
		constraints = [models.CheckConstraint(condition=(
			models.Q(registro__isnull=False, compromiso__isnull=True)
			| models.Q(registro__isnull=True, compromiso__isnull=False)),
            name='evidencia_asociada_a_registro_o_compromiso')]

	def __str__(self):
		return f'Evidencia {self.codigo} ({self.get_estado_display()})'

	def asignarEvidencia(self,registro: Optional[Registro] = None,compromiso: Optional[Compromiso] = None,) -> None:
		"""Asigna esta evidencia a un único registro o compromiso, sin guardarla."""
		if (registro is None) == (compromiso is None):
			raise ValueError('Indica exactamente un registro o un compromiso.')

		self.registro = registro
		self.compromiso = compromiso
	

#Modelo de Revisión de Evidencia
class RevisionEvidencia(models.Model):
	class Decision(models.TextChoices):
		APROBADA = 'aprobada', 'Aprobada'
		RECHAZADA = 'rechazada', 'Rechazada'
		CORRECCION = 'correccion', 'Solicitar corrección'

	evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name='revisiones')
	verificador = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='revisiones_evidencia',
	)
	decision = models.CharField(max_length=16, choices=Decision.choices)
	observaciones = models.TextField(blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-fecha']
		db_table = "revision_evidencia"
		verbose_name = 'revision_evidencia'
		verbose_name_plural = 'revision_evidencias'

	def __str__(self):
		return f'{self.get_decision_display()} - {self.evidencia.codigo}'
