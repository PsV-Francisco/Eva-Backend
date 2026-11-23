from tempfile import TemporaryDirectory
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse

from AdminApp.models import (
	Cargo,
	Catalogo,
	Delegacion,
	Alerta,
	Comentarios,
	Historial,
	ParametroSistema,
	Rol,
)
from AdminApp.roles import ensure_role_group
from AdminApp.forms import RolForm
from config.permissions import PERMISSION_CATALOG
from CoordinadorApp.models import Desempeno, Funcion, Item, Periodo
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
			('funcionario:home', 'funcionario', 'Tablero Personal'),
			('supervisor:home', 'supervisor', 'Validar evidencias'),
			('delegado:home', 'delegado', 'Resumen de la delegación'),
			('coordinador:home', 'coordinador', 'Tablero Personal'),
			('administracion:home', 'administrador', 'Usuarios'),
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
				self.assertContains(response, 'data-role-sidebar')
				self.assertContains(response, 'data-sidebar-section')
				self.assertContains(response, 'data-current="true"')

	def test_each_existing_cargo_keeps_access_with_and_without_an_additional_role(self):
		role_routes = (
			('admin', 'administracion:home'),
			('administrador', 'administracion:home'),
			('coordinador', 'coordinador:home'),
			('delegado', 'delegado:home'),
			('funcionario', 'funcionario:home'),
			('supervisor', 'supervisor:home'),
			('verificador', 'supervisor:home'),
			('vistaf', 'vistaf:home'),
			('consulta', 'vistaf:home'),
			('usuario de consulta', 'vistaf:home'),
		)
		additional_role = Rol.objects.create(nombre='Permiso adicional de consulta')
		permission = Permission.objects.get(
			content_type__app_label='AdminApp',
			codename='view_public_reports',
		)
		ensure_role_group(additional_role).permissions.add(permission)

		for index, (cargo_name, route_name) in enumerate(role_routes):
			with self.subTest(cargo=cargo_name):
				cargo, _ = Cargo.objects.get_or_create(nombre=cargo_name)
				user = get_user_model().objects.create_user(
					email=f'cargo-matriz-{index}@sgr.test',
					password='Sgr-Test-Password-418!',
					cargo=cargo,
				)
				client = Client()
				client.force_login(user)
				route = reverse(route_name)
				response = client.get(route)
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, 'data-role-sidebar')
				self.assertContains(response, 'data-sidebar-section')

				user.roles.add(additional_role)
				response = client.get(route)
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, 'data-role-sidebar')

	def test_administrator_cargo_can_open_each_existing_panel(self):
		panel_routes = (
			'funcionario:home',
			'supervisor:home',
			'delegado:home',
			'coordinador:home',
			'administracion:home',
			'vistaf:home',
		)
		for route_name in panel_routes:
			with self.subTest(route=route_name):
				response = self.client.get(reverse(route_name))
				self.assertEqual(response.status_code, 200)

	def test_every_catalogued_permission_resolves_to_its_protected_view(self):
		for definition in PERMISSION_CATALOG:
			with self.subTest(view=definition.view_name):
				callback = resolve(reverse(
					definition.view_name,
					kwargs=dict(definition.route_kwargs),
				)).func
				self.assertEqual(
					callback.required_permission,
					definition.codename,
				)

	def test_menu_shows_role_granted_views_but_not_unpermitted_admin_views(self):
		permission = Permission.objects.get(
			content_type__app_label='AdminApp',
			codename='view_public_reports',
		)
		role = Rol.objects.create(nombre='Menú de consulta')
		ensure_role_group(role).permissions.add(permission)
		user = get_user_model().objects.create_user(
			email='menu-por-rol@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=Cargo.objects.create(nombre='Cargo sin menú'),
		)
		user.roles.add(role)
		client = Client()
		client.force_login(user)

		response = client.get(reverse('vistaf:home'))
		self.assertContains(response, 'Consultar información')
		self.assertNotContains(response, 'Administrar usuarios')

	def test_sidebar_marks_current_section_and_hides_empty_sections(self):
		cargo = Cargo.objects.create(nombre='consulta')
		user = get_user_model().objects.create_user(
			email='sidebar-consulta@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=cargo,
		)
		client = Client()
		client.force_login(user)
		response = client.get(reverse('vistaf:home'))
		self.assertContains(
			response,
			'data-section-key="consulta" data-current="true" open',
		)
		self.assertContains(response, 'aria-expanded="true"')
		self.assertNotContains(response, 'data-section-key="usuarios"')
		self.assertNotContains(response, 'Administrar usuarios')

	def test_sidebar_groups_administrator_options_without_empty_sections(self):
		response = self.client.get(reverse('administracion:home'))
		self.assertContains(response, 'data-section-key="organizacion"')
		self.assertContains(response, 'data-section-key="metas-seguimiento"')
		self.assertNotContains(response, 'data-section-key="atenciones"')
		self.assertContains(response, 'data-section-key="operacion"')
		self.assertContains(response, 'data-section-key="territorio"')
		self.assertContains(response, 'data-section-key="auditoria"')
		self.assertContains(response, 'data-section-key="ayuda"')

	def test_role_form_saves_selected_permissions(self):
		permissions = Permission.objects.filter(
			content_type__app_label='AdminApp',
			codename__in=('access_admin_roles', 'view_public_reports'),
		).order_by('codename')
		role = Rol.objects.create(nombre='Rol selector')
		form = RolForm(
			data={
				'nombre': role.nombre,
				'descripcion': 'Permisos seleccionados',
				'alcance': Rol.Alcance.GLOBAL,
				'estado': Rol.Estado.ACTIVO,
				'permissions': [str(permission.pk) for permission in permissions],
			},
			instance=role,
			actor=self.admin,
		)
		self.assertTrue(form.is_valid(), form.errors)
		form.save()
		self.assertQuerySetEqual(
			role.grupo.permissions.order_by('codename'),
			permissions,
			transform=lambda item: item,
		)

	def test_role_form_loads_existing_permissions_when_editing(self):
		permission = Permission.objects.get(
			content_type__app_label='AdminApp',
			codename='access_admin_roles',
		)
		role = Rol.objects.create(nombre='Rol existente')
		ensure_role_group(role).permissions.add(permission)
		form = RolForm(instance=role, actor=self.admin)
		self.assertIn(permission.pk, form.initial['permissions'])
		group = next(
			group for group in form.permission_groups
			if any(
				str(option['value']) == str(permission.pk)
				for option in group['choices']
			)
		)
		selected = [
			option['value']
			for option in group['choices']
			if option['selected']
		]
		self.assertIn(str(permission.pk), [str(value) for value in selected])

	def test_role_form_rejects_permissions_outside_actor_authority(self):
		actor = get_user_model().objects.create_user(
			email='role-editor@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=Cargo.objects.create(nombre='funcionario'),
		)
		permission = Permission.objects.get(
			content_type__app_label='AdminApp',
			codename='access_admin_roles',
		)
		form = RolForm(
			data={
				'nombre': 'Rol no autorizado',
				'descripcion': '',
				'alcance': Rol.Alcance.GLOBAL,
				'estado': Rol.Estado.ACTIVO,
				'permissions': [permission.pk],
			},
			actor=actor,
		)
		self.assertFalse(form.is_valid())
		self.assertIn('permissions', form.errors)

	def test_roles_page_renders_visible_permission_checkboxes(self):
		response = self.client.get(reverse('administracion:roles'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-permission-selector')
		self.assertContains(response, 'type="checkbox"')
		self.assertContains(response, 'data-permission-search')
		self.assertContains(response, 'data-module-select')
		self.assertContains(response, 'data-permission-description')

	def test_role_form_keeps_selected_permissions_after_validation_error(self):
		permission = Permission.objects.get(
			content_type__app_label='AdminApp',
			codename='access_admin_roles',
		)
		form = RolForm(
			data={
				'nombre': '',
				'descripcion': '',
				'alcance': Rol.Alcance.GLOBAL,
				'estado': Rol.Estado.ACTIVO,
				'permissions': [permission.pk],
			},
			actor=self.admin,
		)
		self.assertFalse(form.is_valid())
		selected = [
			str(option['value'])
			for group in form.permission_groups
			for option in group['choices']
			if option['selected']
		]
		self.assertEqual(selected, [str(permission.pk)])

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
		self.assertRedirects(response, reverse('administracion:dashboard'))

	def test_role_workspaces_require_authentication(self):
		client = Client()
		for route in ('funcionario:home', 'supervisor:home', 'delegado:home', 'coordinador:home', 'vistaf:home'):
			with self.subTest(route=route):
				response = client.get(reverse(route))
				self.assertEqual(response.status_code, 302)
				self.assertTrue(response.url.startswith('/?next='))

	def test_switching_delegation_uses_only_authorized_options(self):
		primary = Delegacion.objects.create(nombre='Delegación principal')
		secondary = Delegacion.objects.create(nombre='Delegación secundaria')
		unauthorized = Delegacion.objects.create(nombre='Delegación no autorizada')
		user = get_user_model().objects.create_user(
			email='multi-delegacion@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=Cargo.objects.get(nombre='administrador'),
			delegacion=primary,
		)
		user.delegaciones_autorizadas.add(secondary)
		client = Client()
		client.force_login(user)

		response = client.get(reverse('administracion:home'))
		self.assertContains(response, f'{primary.codigo}</strong>')
		self.assertContains(response, primary.nombre)
		self.assertContains(response, secondary.nombre)
		header_selector = response.content.decode().split(
			'<select id="active-delegation"',
		)[1].split('</select>', 1)[0]
		self.assertNotIn(unauthorized.nombre, header_selector)

		response = client.post(reverse('select_active_delegation'), {
			'delegacion': secondary.pk,
			'next': reverse('administracion:home'),
		})
		self.assertRedirects(response, reverse('administracion:home'))
		response = client.get(reverse('administracion:home'))
		self.assertContains(response, f'{secondary.codigo}</strong>')
		self.assertContains(response, secondary.nombre)

		response = client.post(reverse('select_active_delegation'), {
			'delegacion': unauthorized.pk,
			'next': reverse('administracion:home'),
		})
		self.assertRedirects(response, reverse('administracion:home'))
		self.assertEqual(
			client.session['active_delegation_id'],
			secondary.pk,
		)

	def test_switching_delegation_changes_delegation_scoped_lists(self):
		primary = Delegacion.objects.create(nombre='Delegación de origen')
		secondary = Delegacion.objects.create(nombre='Delegación seleccionada')
		user = get_user_model().objects.create_user(
			email='delegado-multiple@sgr.test',
			password='Sgr-Test-Password-418!',
			cargo=Cargo.objects.create(nombre='delegado'),
			delegacion=primary,
		)
		user.delegaciones_autorizadas.add(secondary)
		period = Periodo.objects.create(
			nombre='Período selector delegación',
			fecha_inicio=date.today(),
			fecha_fin=date.today() + timedelta(days=30),
		)
		primary_agenda = Agenda.objects.create(
			delegacion=primary, periodo=period,
		)
		secondary_agenda = Agenda.objects.create(
			delegacion=secondary, periodo=period,
		)
		Compromiso.objects.create(
			agenda=primary_agenda,
			descripcion='Compromiso delegación origen',
			fecha=date.today(),
		)
		Compromiso.objects.create(
			agenda=secondary_agenda,
			descripcion='Compromiso delegación seleccionada',
			fecha=date.today(),
		)
		client = Client()
		client.force_login(user)

		response = client.get(reverse('delegado:home'))
		self.assertContains(response, 'Compromiso delegación origen')
		self.assertNotContains(response, 'Compromiso delegación seleccionada')

		client.post(reverse('select_active_delegation'), {
			'delegacion': secondary.pk,
			'next': reverse('delegado:home'),
		})
		response = client.get(reverse('delegado:home'))
		self.assertContains(response, 'Compromiso delegación seleccionada')
		self.assertNotContains(response, 'Compromiso delegación origen')

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

	def test_manual_access_by_profile_and_403_for_unauthorized_role(self):
		role_names = (
			('administrador', 'Administrador'),
			('coordinador', 'Coordinador'),
			('delegado', 'Delegado'),
			('funcionario', 'Funcionario'),
			('supervisor', 'Verificador / Supervisor'),
		)
		for cargo_name, label in role_names:
			with self.subTest(cargo=cargo_name):
				cargo, _ = Cargo.objects.get_or_create(nombre=cargo_name)
				user = get_user_model().objects.create_user(
					email=f'{cargo_name}@sgr.test',
					password='Sgr-Test-Password-418!',
					cargo=cargo,
				)
				client = Client()
				client.force_login(user)
				response = client.get(reverse('manual'))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, label)
				for other_cargo, _ in role_names:
					if cargo_name == other_cargo:
						continue
					response = client.get(reverse('manual_role', args=[other_cargo]))
					if cargo_name == 'administrador':
						self.assertEqual(response.status_code, 200)
					else:
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
			response = self.client.post(reverse('funcionario:gestion_actividades'), {
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
			self.assertRedirects(response, reverse('funcionario:gestion_actividades'))
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
		response = self.client.post(reverse('funcionario:gestion_actividades'), payload)
		self.assertRedirects(response, reverse('funcionario:gestion_actividades'))
		registro.refresh_from_db()
		self.assertEqual(registro.descripcion, 'Descripción actualizada')

		response = self.client.post(reverse('funcionario:gestion_actividades'), {
			'action': 'eliminar', 'registro_id': registro.pk,
		})
		self.assertRedirects(response, reverse('funcionario:gestion_actividades'))
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


class TargetSchemaAdminModelTests(TestCase):
	def setUp(self):
		self.autor = get_user_model().objects.create_user(
			email='autor-comentario@sgr.test',
			password='Sgr-Test-Password-418!',
		)
		self.destinatario = get_user_model().objects.create_user(
			email='destinatario-alerta@sgr.test',
			password='Sgr-Test-Password-418!',
		)
		self.periodo = Periodo.objects.create(
			nombre='Período comentarios',
			fecha_inicio='2026-01-01',
			fecha_fin='2026-12-31',
		)
		self.funcion = Funcion.objects.create(nombre='Función comentarios')
		self.item = Item.objects.create(
			funcion=self.funcion,
			nombre='Ítem comentarios',
		)
		self.registro = Registro.objects.create(
			fecha='2026-05-01',
			item=self.item,
			periodo=self.periodo,
			descripcion='Registro para comentario',
			autor=self.autor,
		)
		self.delegacion = Delegacion.objects.create(nombre='Delegación comentarios')
		self.agenda = Agenda.objects.create(
			delegacion=self.delegacion,
			periodo=self.periodo,
		)
		self.compromiso = Compromiso.objects.create(
			agenda=self.agenda,
			descripcion='Compromiso para comentario',
			fecha='2026-05-02',
		)
		self.compromiso.responsables.add(self.autor)

	def create_comment(self, **overrides):
		values = {
			'texto': 'Comentario de prueba',
			'fecha': '2026-05-03T12:00:00Z',
			'autor': self.autor,
		}
		values.update(overrides)
		return Comentarios.objects.create(**values)

	def test_alerta_creation_and_nullable_link(self):
		alerta = Alerta.objects.create(
			motivo='Aviso',
			fecha='2026-05-03T12:00:00Z',
			estado='pendiente',
			enlace=None,
			destinatario=self.destinatario,
		)

		alerta.refresh_from_db()
		self.assertEqual(alerta.destinatario, self.destinatario)
		self.assertIsNone(alerta.enlace)
		self.assertEqual(self.destinatario.alertas_recibidas.get(), alerta)

	def test_alerta_protects_its_recipient(self):
		Alerta.objects.create(
			motivo='Aviso protegido',
			fecha='2026-05-03T12:00:00Z',
			estado='pendiente',
			destinatario=self.destinatario,
		)

		with self.assertRaises(ProtectedError):
			self.destinatario.delete()

	def test_comment_with_registration_copies_registration_dimensions(self):
		comentario = self.create_comment(registro=self.registro)

		comentario.refresh_from_db()
		self.assertEqual(comentario.autor_registro, self.autor)
		self.assertEqual(comentario.item_registro, self.item)
		self.assertEqual(comentario.periodo_registro, self.periodo)
		self.assertIsNone(comentario.compromiso_id)
		self.assertIsNone(comentario.responsable_compromiso_id)
		self.assertIsNone(comentario.agenda_compromiso_id)
		self.assertIsNone(comentario.periodo_agenda_compromiso_id)
		self.assertIsNone(comentario.agenda_delegacion_compromiso_id)

	def test_comment_with_commitment_copies_commitment_dimensions(self):
		comentario = self.create_comment(compromiso=self.compromiso)

		comentario.refresh_from_db()
		self.assertIsNone(comentario.registro_id)
		self.assertIsNone(comentario.autor_registro_id)
		self.assertIsNone(comentario.item_registro_id)
		self.assertIsNone(comentario.periodo_registro_id)
		self.assertEqual(comentario.responsable_compromiso, self.autor)
		self.assertEqual(comentario.agenda_compromiso, self.agenda)
		self.assertEqual(comentario.periodo_agenda_compromiso, self.periodo)
		self.assertEqual(comentario.agenda_delegacion_compromiso, self.delegacion)

	def test_comment_with_both_parents_copies_both_dimension_groups(self):
		comentario = self.create_comment(
			registro=self.registro,
			compromiso=self.compromiso,
		)

		comentario.refresh_from_db()
		self.assertEqual(comentario.autor_registro, self.autor)
		self.assertEqual(comentario.item_registro, self.item)
		self.assertEqual(comentario.periodo_registro, self.periodo)
		self.assertEqual(comentario.agenda_compromiso, self.agenda)

	def test_comment_without_either_parent_is_rejected(self):
		comentario = Comentarios(
			texto='Comentario sin relación',
			fecha='2026-05-03T12:00:00Z',
			autor=self.autor,
		)

		with self.assertRaises(ValidationError):
			comentario.save()

	def test_comment_with_multiple_commitment_responsibles_keeps_responsible_null(self):
		other_user = get_user_model().objects.create_user(
			email='otro-responsable@sgr.test',
			password='Sgr-Test-Password-418!',
		)
		self.compromiso.responsables.add(other_user)

		comentario = self.create_comment(compromiso=self.compromiso)

		comentario.refresh_from_db()
		self.assertIsNone(comentario.responsable_compromiso_id)

	def test_comment_clean_rejects_inconsistent_registration_dimensions(self):
		comentario = Comentarios(
			texto='Comentario inconsistente',
			fecha='2026-05-03T12:00:00Z',
			autor=self.autor,
			registro=self.registro,
			autor_registro=self.destinatario,
		)

		with self.assertRaises(ValidationError) as raised:
			comentario.clean()

		self.assertIn('autor_registro', raised.exception.error_dict)

	def test_comment_save_with_update_fields_persists_derived_dimensions(self):
		comentario = self.create_comment(registro=self.registro)
		comentario.registro = None
		comentario.compromiso = self.compromiso
		comentario.save(update_fields=['registro', 'compromiso'])
		comentario.refresh_from_db()

		self.assertIsNone(comentario.autor_registro_id)
		self.assertIsNone(comentario.item_registro_id)
		self.assertEqual(comentario.agenda_compromiso, self.agenda)

	def test_comment_protects_related_records_and_commitment_graph(self):
		self.create_comment(registro=self.registro, compromiso=self.compromiso)

		for related in (
			self.registro,
			self.item,
			self.periodo,
			self.compromiso,
			self.agenda,
			self.delegacion,
			self.autor,
		):
			with self.subTest(model=type(related).__name__):
				with self.assertRaises(ProtectedError):
					related.delete()
