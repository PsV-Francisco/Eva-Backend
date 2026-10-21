from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from AdminApp.models import (
	Cargo,
	Catalogo,
	Delegacion,
	Historial,
	ParametroSistema,
	Rol,
)
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
			('funcionario:home', 'funcionario', 'Registro de Actividades'),
			('supervisor:home', 'supervisor', 'Validar evidencias'),
			('delegado:home', 'delegado', 'Resumen de la delegación'),
			('coordinador:home', 'coordinador', 'Metas e indicadores'),
			('administracion:home', 'administrador', 'Gestión de la medición'),
			('vistaf:home', 'consulta', 'Búsqueda de información'),
		)
		for index, (route, cargo_name, sidebar_label) in enumerate(route_cargos):
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
				self.assertContains(response, sidebar_label)

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
		role = Rol.objects.create(nombre='Gestor de medición')
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
			'roles': [role.pk],
			'csrfmiddlewaretoken': token,
		})
		self.assertEqual(response.status_code, 302)
		created = get_user_model().objects.get(email='funcionario@sgr.test')
		self.assertTrue(created.check_password('Sgr-New-Account-573!'))
		self.assertQuerySetEqual(created.roles.all(), [role], transform=lambda item: item)
		self.assertTrue(Historial.objects.filter(
			accion='Crear usuario',
			entidad_afectada=f'Usuario:{created.pk}',
			autor=self.admin,
		).exists())
		self.assertContains(client.get(reverse('administracion:home')), 'Gestor de medición')

	def test_admin_can_update_and_delete_an_unreferenced_user(self):
		role = Rol.objects.create(nombre='Verificador')
		user = get_user_model().objects.create_user(
			email='antes@sgr.test', password='Sgr-Test-Password-418!',
		)
		response = self.client.post(reverse('administracion:home'), {
			'action': 'guardar',
			'usuario_id': user.pk,
			'email': 'despues@sgr.test',
			'first_name': 'Nombre',
			'last_name': 'Actualizado',
			'is_active': 'on',
			'password1': '',
			'password2': '',
			'roles': [role.pk],
		})
		self.assertEqual(response.status_code, 302)
		user.refresh_from_db()
		self.assertEqual(user.email, 'despues@sgr.test')
		self.assertEqual(list(user.roles.all()), [role])
		update_audit = Historial.objects.get(
			accion='Editar usuario',
			entidad_afectada=f'Usuario:{user.pk}',
		)
		self.assertEqual(update_audit.valor_anterior['email'], 'antes@sgr.test')
		self.assertEqual(update_audit.valor_nuevo['roles'], [role.pk])

		response = self.client.post(reverse('administracion:home'), {
			'action': 'eliminar', 'usuario_id': user.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())
		self.assertTrue(Historial.objects.filter(
			accion='Eliminar usuario',
			entidad_afectada=f'Usuario:{user.pk}',
		).exists())

	def test_admin_parameter_changes_are_validated_and_audited(self):
		response = self.client.post(reverse('administracion:parametros'), {
			'tope_cumplimiento': '175.00',
			'umbral_delegacion': '75.00',
		})

		self.assertEqual(response.status_code, 302)
		self.assertEqual(
			ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO),
			175,
		)
		self.assertEqual(
			ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION),
			75,
		)
		audit = Historial.objects.get(
			accion='Cambiar parámetro del sistema',
			entidad_afectada='ParametroSistema:tope_cumplimiento',
		)
		self.assertEqual(audit.autor, self.admin)
		self.assertEqual(audit.valor_anterior['valor'], '150')
		self.assertEqual(audit.valor_nuevo['valor'], '175.00')

	def test_parameter_changes_require_administrator_cargo(self):
		self.admin.cargo = Cargo.objects.create(nombre='funcionario')
		self.admin.save(update_fields=['cargo'])

		response = self.client.post(reverse('administracion:parametros'), {
			'tope_cumplimiento': '175',
			'umbral_delegacion': '75',
		})

		self.assertEqual(response.status_code, 403)
		self.assertFalse(ParametroSistema.objects.exists())

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

	def test_coordinator_can_update_and_delete_an_unused_period(self):
		self.admin.cargo = Cargo.objects.create(nombre='coordinador')
		self.admin.save(update_fields=['cargo'])
		period = Periodo.objects.create(
			nombre='Período inicial', fecha_inicio='2026-10-01',
			fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
		)
		response = self.client.post(reverse('coordinador:home'), {
			'action': 'guardar',
			'periodo_id': period.pk,
			'nombre': 'Período actualizado',
			'fecha_inicio': '2026-10-02',
			'fecha_fin': '2026-12-31',
			'estado': Periodo.Estado.ABIERTO,
		})
		self.assertEqual(response.status_code, 302)
		period.refresh_from_db()
		self.assertEqual(period.nombre, 'Período actualizado')

		response = self.client.post(reverse('coordinador:home'), {
			'action': 'eliminar', 'periodo_id': period.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Periodo.objects.filter(pk=period.pk).exists())

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
					'respaldo.pdf', b'%PDF-1.4\ncontenido ficticio',
					content_type='application/pdf',
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

	def test_employee_can_update_and_delete_own_unreviewed_activity(self):
		period = Periodo.objects.create(
			nombre='Período CRUD', fecha_inicio='2026-10-01',
			fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
		)
		function = Funcion.objects.create(nombre='Función CRUD')
		item = Item.objects.create(funcion=function, nombre='Ítem CRUD')
		catalogo = Catalogo.objects.create(actividad='Actividad CRUD', servicio='Servicio CRUD')
		self.admin.cargo = Cargo.objects.create(nombre='funcionario', funciones=function)
		self.admin.save(update_fields=['cargo'])
		registro = Registro.objects.create(
			fecha='2026-10-02', periodo=period, item=item, catalogo=catalogo,
			descripcion='Descripción original', accion='Acción inicial',
			autor=self.admin,
		)
		payload = {
			'action': 'guardar', 'registro_id': registro.pk,
			'fecha': '2026-10-02', 'periodo': period.pk, 'item': item.pk,
			'catalogo': catalogo.pk, 'descripcion': 'Descripción actualizada',
			'accion': 'Acción actualizada', 'contacto': '', 'telefono': '',
			'incluir_en_agenda': '',
		}
		response = self.client.post(reverse('funcionario:home'), payload)
		self.assertEqual(response.status_code, 302)
		registro.refresh_from_db()
		self.assertEqual(registro.descripcion, 'Descripción actualizada')

		response = self.client.post(reverse('funcionario:home'), {
			'action': 'eliminar', 'registro_id': registro.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Registro.objects.filter(pk=registro.pk).exists())

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

	def test_delegate_can_update_and_delete_commitments_without_evidence(self):
		delegation = Delegacion.objects.create(nombre='Delegación CRUD', estado='activa')
		self.admin.cargo = Cargo.objects.create(nombre='delegado')
		self.admin.delegacion = delegation
		self.admin.save(update_fields=['cargo', 'delegacion'])
		period = Periodo.objects.create(
			nombre='Agenda CRUD', fecha_inicio='2026-10-01',
			fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
		)
		agenda = Agenda.objects.create(delegacion=delegation, periodo=period)
		commitment = Compromiso.objects.create(
			agenda=agenda, descripcion='Compromiso inicial',
			fecha='2026-10-20', estado=Compromiso.Estado.INGRESADO,
		)
		commitment.responsables.add(self.admin)
		response = self.client.post(reverse('delegado:home'), {
			'action': 'guardar', 'compromiso_id': commitment.pk,
			'periodo': period.pk, 'descripcion': 'Compromiso actualizado',
			'solicitante': 'Equipo', 'territorio': 'Norte',
			'fecha': '2026-10-21', 'responsables': [self.admin.pk],
			'estado': Compromiso.Estado.PENDIENTE, 'observaciones': '',
		})
		self.assertEqual(response.status_code, 302)
		commitment.refresh_from_db()
		self.assertEqual(commitment.descripcion, 'Compromiso actualizado')

		response = self.client.post(reverse('delegado:home'), {
			'action': 'eliminar', 'compromiso_id': commitment.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Compromiso.objects.filter(pk=commitment.pk).exists())
