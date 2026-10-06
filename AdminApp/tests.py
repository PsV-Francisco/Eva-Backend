from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from AdminApp.models import Cargo, Catalogo, Delegacion, Rol
from CoordinadorApp.models import Funcion, Item, Periodo
from DelegadoApp.models import Agenda, Compromiso
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia, RevisionEvidencia


class RolePortalTests(TestCase):
	def setUp(self):
		self.admin = get_user_model().objects.create_superuser(
			email='admin@sgr.test', password='Sgr-Test-Password-418!'
		)
		self.admin.cargo = Cargo.objects.create(nombre='administrador')
		self.admin.save(update_fields=['cargo'])
		self.client.force_login(self.admin)

	def test_all_role_workspaces_render(self):
		route_cargos = (
			('funcionario:home', 'funcionario'),
			('supervisor:home', 'supervisor'),
			('delegado:home', 'delegado'),
			('coordinador:home', 'coordinador'),
			('administracion:home', 'administrador'),
			('vistaf:home', 'consulta'),
		)
		for index, (route, cargo_name) in enumerate(route_cargos):
			with self.subTest(route=route):
				cargo, _ = Cargo.objects.get_or_create(nombre=cargo_name)
				user = get_user_model().objects.create_user(
					email=f'cargo-{index}@sgr.test',
					password='Sgr-Test-Password-418!',
					cargo=cargo,
				)
				client = Client()
				client.force_login(user)
				response = client.get(reverse(route))
				self.assertEqual(response.status_code, 200)

	def test_root_shows_login_and_authenticates_demo_user(self):
		client = Client()
		response = client.get(reverse('login'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="csrfmiddlewaretoken"')
		self.assertContains(response, 'Correo electrónico')

		response = client.post(reverse('login'), {
			'username': self.admin.email,
			'password': 'Sgr-Test-Password-418!',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('home'))
		response = client.get(reverse('home'))
		self.assertRedirects(response, reverse('administracion:home'))

	def test_role_workspaces_require_authentication(self):
		client = Client()
		for route in ('funcionario:home', 'supervisor:home', 'delegado:home', 'coordinador:home', 'vistaf:home'):
			with self.subTest(route=route):
				response = client.get(reverse(route))
				self.assertEqual(response.status_code, 302)
				self.assertTrue(response.url.startswith('/?next='))

	def test_role_does_not_grant_access_without_matching_cargo(self):
		user = get_user_model().objects.create_user(
			email='sin-cargo@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=Cargo.objects.create(nombre='Otro cargo'),
		)
		user.roles.add(Rol.objects.create(nombre='Funcionario'))
		client = Client()
		client.force_login(user)
		response = client.get(reverse('funcionario:home'))
		self.assertEqual(response.status_code, 403)

	def test_superuser_without_cargo_cannot_access_dashboard(self):
		user = get_user_model().objects.create_superuser(
			email='admin-sin-cargo@sgr.test', password='Sgr-Test-Password-418!'
		)
		client = Client()
		client.force_login(user)
		response = client.get(reverse('administracion:home'))
		self.assertEqual(response.status_code, 403)

	def test_admin_form_requires_csrf_and_creates_hashed_password(self):
		client = Client(enforce_csrf_checks=True)
		client.force_login(self.admin)
		response = client.get(reverse('administracion:home'))
		self.assertEqual(response.status_code, 200)
		token = client.cookies['csrftoken'].value
		response = client.post(reverse('administracion:home'), {
			'email': 'funcionario@sgr.test',
			'first_name': 'Ana',
			'last_name': 'Prueba',
			'password1': 'Sgr-New-Account-573!',
			'password2': 'Sgr-New-Account-573!',
			'is_active': 'on',
			'csrfmiddlewaretoken': token,
		})
		self.assertEqual(response.status_code, 302)
		created = get_user_model().objects.get(email='funcionario@sgr.test')
		self.assertTrue(created.check_password('Sgr-New-Account-573!'))

	def test_coordinator_can_create_period(self):
		self.admin.cargo = Cargo.objects.create(nombre='coordinador')
		self.admin.save(update_fields=['cargo'])
		response = self.client.post(reverse('coordinador:home'), {
			'nombre': 'Período de prueba',
			'fecha_inicio': '2026-10-01',
			'fecha_fin': '2026-12-31',
			'estado': Periodo.Estado.ABIERTO,
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(Periodo.objects.filter(nombre='Período de prueba').exists())

	def test_employee_can_register_activity_with_evidence_and_supervisor_can_approve(self):
		period = Periodo.objects.create(
			nombre='Período de evidencia', fecha_inicio='2026-10-01',
			fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
		)
		function = Funcion.objects.create(nombre='Atención territorial')
		item = Item.objects.create(funcion=function, nombre='Atenciones')
		catalogo = Catalogo.objects.create(actividad='Atención', servicio='Orientación')
		cargo = Cargo.objects.create(nombre='funcionario', funciones=function)
		self.admin.cargo = cargo
		self.admin.save(update_fields=['cargo'])
		with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			response = self.client.post(reverse('funcionario:home'), {
				'fecha': '2026-10-01',
				'periodo': period.pk,
				'item': item.pk,
				'catalogo': catalogo.pk,
				'descripcion': 'Orientación a usuario',
				'accion': 'Se entregó orientación y seguimiento.',
				'contacto': '',
				'telefono': '',
				'incluir_en_agenda': '',
				'evidencia': SimpleUploadedFile(
					'respaldo.pdf', b'contenido ficticio', content_type='application/pdf',
				),
			})
			self.assertEqual(response.status_code, 302)
			registro = Registro.objects.get(autor=self.admin)
			evidencia = Evidencia.objects.get(registro=registro)
			self.assertEqual(registro.estado, Registro.Estado.PENDIENTE)

			self.admin.cargo = Cargo.objects.create(nombre='supervisor')
			self.admin.save(update_fields=['cargo'])
			response = self.client.post(reverse('supervisor:home'), {
				'evidencia_id': evidencia.pk,
				'decision': RevisionEvidencia.Decision.APROBADA,
				'observaciones': 'Respaldo revisado.',
			})
			self.assertEqual(response.status_code, 302)
			evidencia.refresh_from_db()
			registro.refresh_from_db()
			self.assertEqual(evidencia.estado, Evidencia.Estado.APROBADA)
			self.assertEqual(registro.estado, Registro.Estado.VALIDADA)
			self.assertEqual(RevisionEvidencia.objects.filter(evidencia=evidencia).count(), 1)

	def test_delegate_can_create_commitment_for_their_delegation(self):
		delegation = Delegacion.objects.create(nombre='Delegación de prueba', estado='activa')
		self.admin.cargo = Cargo.objects.create(nombre='delegado')
		self.admin.delegacion = delegation
		self.admin.save(update_fields=['cargo', 'delegacion'])
		period = Periodo.objects.create(
			nombre='Agenda de prueba', fecha_inicio='2026-10-01',
			fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
		)
		response = self.client.post(reverse('delegado:home'), {
			'periodo': period.pk,
			'descripcion': 'Coordinar operativo',
			'solicitante': 'Equipo territorial',
			'territorio': 'Sector norte',
			'fecha': '2026-10-20',
			'responsables': [self.admin.pk],
			'estado': Compromiso.Estado.INGRESADO,
			'observaciones': '',
		})
		self.assertEqual(response.status_code, 302)
		agenda = Agenda.objects.get(delegacion=delegation, periodo=period)
		commitment = Compromiso.objects.get(agenda=agenda)
		self.assertEqual(commitment.responsables.get(), self.admin)
