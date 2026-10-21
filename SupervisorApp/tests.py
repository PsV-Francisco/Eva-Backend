from django.core.files.uploadedfile import SimpleUploadedFile
from django import forms
from django.test import SimpleTestCase
from django.db.models.base import ModelState
from unittest.mock import Mock

from DelegadoApp.models import Compromiso
from FuncionarioApp.models import GestionAtencion, Registro
from SupervisorApp.files import validate_evidence_file
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
		self.atencion = Mock(spec=GestionAtencion)
		self.atencion._state = ModelState()
		self.atencion.pk = 3

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

	def test_assigns_only_social_attention(self):
		self.evidencia.asignarEvidencia(gestion_atencion=self.atencion)

		self.assertIs(self.evidencia.gestion_atencion, self.atencion)
		self.assertIsNone(self.evidencia.registro)
		self.assertIsNone(self.evidencia.compromiso)

	def test_rejects_multiple_targets_including_attention(self):
		with self.assertRaises(ValueError):
			self.evidencia.asignarEvidencia(
				registro=self.registro,
				gestion_atencion=self.atencion,
			)

	def test_rejects_missing_target(self):
		with self.assertRaises(ValueError):
			self.evidencia.asignarEvidencia()


class EvidenceFileValidationTests(SimpleTestCase):
	def test_accepts_pdf_with_pdf_signature(self):
		uploaded = SimpleUploadedFile(
			'respaldo.pdf',
			b'%PDF-1.4\ncontenido',
			content_type='application/octet-stream',
		)

		self.assertIs(validate_evidence_file(uploaded), uploaded)

	def test_rejects_fake_pdf_and_disallowed_extension(self):
		for filename, content in (
			('imagen.pdf', b'no es un pdf'),
			('script.exe', b'%PDF-1.4'),
		):
			with self.subTest(filename=filename):
				with self.assertRaises(forms.ValidationError):
					validate_evidence_file(SimpleUploadedFile(filename, content))

	def test_rejects_files_over_five_megabytes(self):
		uploaded = SimpleUploadedFile(
			'grande.pdf',
			b'%PDF-' + b'0' * (5 * 1024 * 1024),
		)

		with self.assertRaises(forms.ValidationError):
			validate_evidence_file(uploaded)
