from django.test import SimpleTestCase
from django.db.models.base import ModelState
from unittest.mock import Mock

from DelegadoApp.models import Compromiso
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


class AsignarEvidenciaTests(SimpleTestCase):
	def setUp(self):
		self.evidencia = Evidencia()
		self.registro = Mock(spec=Registro)
		self.registro._state = ModelState()
		self.registro.pk = 1
		self.compromiso = Mock(spec=Compromiso)
		self.compromiso._state = ModelState()
		self.compromiso.pk = 2

	def test_assigns_only_the_record(self):
		self.evidencia.asignarEvidencia(registro=self.registro)

		self.assertIs(self.evidencia.registro, self.registro)
		self.assertIsNone(self.evidencia.compromiso)

	def test_assigns_only_the_commitment(self):
		self.evidencia.asignarEvidencia(compromiso=self.compromiso)

		self.assertIsNone(self.evidencia.registro)
		self.assertIs(self.evidencia.compromiso, self.compromiso)

	def test_rejects_both_targets(self):
		with self.assertRaises(ValueError):
			self.evidencia.asignarEvidencia(self.registro, self.compromiso)

	def test_rejects_missing_target(self):
		with self.assertRaises(ValueError):
			self.evidencia.asignarEvidencia()
