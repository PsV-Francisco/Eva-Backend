from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from AdminApp.models import (
    Cargo,
    Delegacion,
    Historial,
    Rol,
    UsuarioCargo,
    UsuarioDelegacion,
)
from AdminApp.roles import ensure_role_group
from CoordinadorApp.models import Desempeno, Funcion, Item, Periodo
from FuncionarioApp.models import Subtipo, Tipo
from config.delegations import authorized_delegations
from test_helpers import create_user


class MaintainerTests(TestCase):
    def setUp(self):
        self.admin = create_user(
            email='admin-maintainers@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_maintainer_routes_render_for_authorized_administrator(self):
        route_names = (
            'delegaciones',
            'roles',
            'items',
            'tipos-atencion',
            'subatenciones',
            'metas',
        )
        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(f'administracion:{route_name}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Exportar a Excel')
        role_page = self.client.get(reverse('administracion:roles'))
        self.assertContains(role_page, 'Administración')
        self.assertContains(role_page, 'Funcionario')
        self.assertContains(role_page, 'name="permissions"')
        self.assertContains(role_page, 'Buscar por permiso')
        self.assertContains(role_page, 'Revisar y validar evidencias de actividades.')
        self.assertContains(role_page, 'Seleccionar todo')

    def test_non_administrator_cannot_open_administration_routes(self):
        user = create_user(
            email='funcionario-maintainers@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.client.force_login(user)

        response = self.client.get(reverse('administracion:roles'))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Rol.objects.exists())

    def test_delegation_crud_uses_real_code_and_audits_changes(self):
        response = self.client.post(reverse('administracion:delegaciones'), {
            'action': 'guardar',
            'codigo': 'DEL-CENTRO',
            'nombre': 'Delegación Centro',
            'direccion': 'Calle 1',
            'comuna': 'La Serena',
            'estado': Delegacion.Estado.ACTIVA,
        })
        self.assertRedirects(response, reverse('administracion:delegaciones'))
        delegation = Delegacion.objects.get(codigo='DEL-CENTRO')
        self.assertEqual(delegation.codigo, 'DEL-CENTRO')
        self.assertTrue(
            Historial.objects.filter(
                accion='Crear delegaciones',
                entidad_afectada=f'Delegacion:{delegation.pk}',
            ).exists()
        )

        response = self.client.post(reverse('administracion:delegaciones'), {
            'action': 'cambiar_estado',
            'object_id': delegation.pk,
        })
        self.assertRedirects(response, reverse('administracion:delegaciones'))
        delegation.refresh_from_db()
        self.assertEqual(delegation.estado, Delegacion.Estado.INACTIVA)

    def test_delegation_code_is_backfilled_for_legacy_model_creations(self):
        delegation = Delegacion.objects.create(nombre='Código automático')
        self.assertEqual(delegation.codigo, f'DEL-{delegation.pk:04d}')

    def test_role_form_persists_description_permissions_scope_and_state(self):
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='manage_periods',
        )
        response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'nombre': 'Coordinador Territorial',
            'descripcion': 'Gestión de una delegación',
            'permissions': [permission.pk],
            'alcance': Rol.Alcance.DELEGACION,
            'estado': Rol.Estado.ACTIVO,
        })

        self.assertRedirects(response, reverse('administracion:roles'))
        role = Rol.objects.get(nombre='Coordinador Territorial')
        self.assertTrue(role.grupo.permissions.filter(pk=permission.pk).exists())
        self.assertEqual(role.alcance, Rol.Alcance.DELEGACION)
        self.assertEqual(role.descripcion, 'Gestión de una delegación')
        self.assertTrue(
            Historial.objects.filter(
                accion='Crear roles y permisos',
                entidad_afectada=f'Rol:{role.pk}',
            ).exists()
        )

        updated_permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='view_public_reports',
        )
        response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'object_id': role.pk,
            'nombre': 'Coordinador Territorial',
            'descripcion': 'Descripción actualizada',
            'permissions': [updated_permission.pk],
            'alcance': Rol.Alcance.DELEGACION,
            'estado': Rol.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:roles'))
        role.refresh_from_db()
        self.assertEqual(role.descripcion, 'Descripción actualizada')
        self.assertEqual(
            list(role.grupo.permissions.values_list('codename', flat=True)),
            ['view_public_reports'],
        )
        self.assertTrue(
            Historial.objects.filter(
                accion='Editar roles y permisos',
                entidad_afectada=f'Rol:{role.pk}',
            ).exists()
        )

    def test_role_form_shows_existing_permissions_and_preserves_selection_on_error(self):
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='manage_periods',
        )
        role = Rol.objects.create(nombre='Rol con período')
        ensure_role_group(role).permissions.add(permission)

        edit_response = self.client.get(
            reverse('administracion:roles'),
            {'editar': role.pk},
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertTrue(any(
            group['selected_count'] == 1
            for group in edit_response.context['form'].permission_groups
        ))
        self.assertContains(edit_response, 'checked')

        error_response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'nombre': 'Administrador del sistema',
            'descripcion': '',
            'permissions': [permission.pk],
            'alcance': Rol.Alcance.GLOBAL,
            'estado': Rol.Estado.ACTIVO,
        })
        self.assertEqual(error_response.status_code, 200)
        self.assertIn(
            str(permission.pk),
            [str(value) for value in error_response.context['form']['permissions'].value()],
        )
        self.assertIn(
            'checked',
            str(error_response.context['form']['permissions']),
        )

    def test_role_form_rejects_permissions_outside_the_catalog(self):
        invalid_permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='add_rol',
        )
        response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'nombre': 'Rol con permiso ajeno',
            'descripcion': '',
            'permissions': [invalid_permission.pk],
            'alcance': Rol.Alcance.GLOBAL,
            'estado': Rol.Estado.ACTIVO,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Rol.objects.filter(nombre='Rol con permiso ajeno').exists())
        self.assertIn('permissions', response.context['form'].errors)

    def test_role_permissions_are_applied_through_groups_and_revocable(self):
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='view_public_reports',
        )
        role = Rol.objects.create(nombre='Consulta adicional')
        user = create_user(
            email='consulta-adicional@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='Cargo adicional'),
        )
        ensure_role_group(role).permissions.add(permission)
        user.roles.add(role)
        client = Client()
        client.force_login(user)

        response = client.get(reverse('vistaf:home'))
        self.assertEqual(response.status_code, 200)

        role.estado = Rol.Estado.INACTIVO
        role.save(update_fields=['estado'])
        self.assertFalse(user.groups.filter(pk=role.grupo_id).exists())
        self.assertEqual(
            client.get(reverse('vistaf:home')).status_code,
            403,
        )

        role.estado = Rol.Estado.ACTIVO
        role.save(update_fields=['estado'])
        self.assertTrue(user.groups.filter(pk=role.grupo_id).exists())
        role.grupo.permissions.remove(permission)
        response = client.get(reverse('vistaf:home'))
        self.assertEqual(response.status_code, 403)

    def test_role_duplication_and_deletion_are_audited(self):
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='manage_periods',
        )
        role = Rol.objects.create(nombre='Rol para duplicar')
        ensure_role_group(role).permissions.add(permission)

        response = self.client.post(reverse('administracion:roles'), {
            'action': 'duplicar',
            'object_id': role.pk,
        })
        self.assertEqual(response.status_code, 302)
        duplicate = Rol.objects.get(nombre='Rol para duplicar (copia)')
        self.assertTrue(
            duplicate.grupo.permissions.filter(pk=permission.pk).exists()
        )
        self.assertTrue(
            Historial.objects.filter(
                accion='Duplicar rol',
                entidad_afectada=f'Rol:{duplicate.pk}',
            ).exists()
        )

        response = self.client.post(reverse('administracion:roles'), {
            'action': 'eliminar',
            'object_id': duplicate.pk,
        })
        self.assertRedirects(response, reverse('administracion:roles'))
        self.assertFalse(Rol.objects.filter(pk=duplicate.pk).exists())
        self.assertTrue(
            Historial.objects.filter(
                accion='Eliminar roles y permisos',
                entidad_afectada=f'Rol:{duplicate.pk}',
            ).exists()
        )

    def test_critical_roles_are_protected_in_the_model_and_view(self):
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='manage_periods',
        )
        role = Rol.objects.create(nombre='Rol crítico', protegido=True)
        group = ensure_role_group(role)
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                group.permissions.add(permission)
        role.nombre = 'Rol crítico renombrado'
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                role.save()
        with self.assertRaises(ProtectedError):
            role.delete()
        with self.assertRaises(ProtectedError):
            Rol.objects.filter(pk=role.pk).delete()

        response = self.client.post(reverse('administracion:roles'), {
            'action': 'eliminar',
            'object_id': role.pk,
        }, follow=True)
        self.assertContains(response, 'no se puede eliminar')
        self.assertTrue(Rol.objects.filter(pk=role.pk).exists())
        response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'nombre': 'Administrador del sistema',
            'descripcion': '',
            'permissions': [],
            'alcance': Rol.Alcance.GLOBAL,
            'estado': Rol.Estado.ACTIVO,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Rol.objects.filter(nombre='Administrador del sistema').exists()
        )

    def test_role_assignment_changes_are_audited(self):
        role = Rol.objects.create(nombre='Rol asignable')
        user = create_user(
            email='usuario-con-rol@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        response = self.client.post(reverse('administracion:home'), {
            'usuario_id': user.pk,
            'email': user.email,
            'first_name': '',
            'last_name': '',
            'delegacion': '',
            'delegaciones_autorizadas': [],
            'cargo': user.cargo_id,
            'roles': [role.pk],
            'is_active': 'on',
            'password1': '',
            'password2': '',
        })
        self.assertRedirects(response, reverse('administracion:home'))
        self.assertTrue(
            Historial.objects.filter(
                accion='Cambiar asignación de roles',
                entidad_afectada=f'Usuario:{user.pk}',
            ).exists()
        )
        role.refresh_from_db()
        self.assertTrue(user.groups.filter(pk=role.grupo_id).exists())

    def test_user_manager_cannot_assign_permissions_the_manager_does_not_have(self):
        manager_permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='access_admin_users',
        )
        elevated_permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='manage_periods',
        )
        manager_role = Rol.objects.create(nombre='Administrar usuarios limitada')
        elevated_role = Rol.objects.create(nombre='Coordinación elevada')
        ensure_role_group(manager_role).permissions.add(manager_permission)
        ensure_role_group(elevated_role).permissions.add(elevated_permission)
        actor = create_user(
            email='gestor-limitado@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='Funcionario con permiso'),
        )
        actor.roles.add(manager_role)
        target = create_user(
            email='destinatario-rol@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.get_or_create(nombre='funcionario')[0],
        )
        self.client.force_login(actor)

        response = self.client.post(reverse('administracion:home'), {
            'usuario_id': target.pk,
            'email': target.email,
            'first_name': '',
            'last_name': '',
            'delegacion': '',
            'delegaciones_autorizadas': [],
            'cargo': target.cargo_id,
            'roles': [elevated_role.pk],
            'is_active': 'on',
            'password1': '',
            'password2': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(target.roles.filter(pk=elevated_role.pk).exists())

    def test_last_administrator_is_protected_by_the_user_endpoint_and_model(self):
        admin_cargo = Cargo.objects.get(nombre='administrador')
        target = create_user(
            email='ultimo-administrador@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=admin_cargo,
        )
        self.admin.is_superuser = False
        self.admin.save(update_fields=['is_superuser'])
        UsuarioCargo.objects.filter(
            usuario=self.admin,
            fecha_fin__isnull=True,
        ).update(fecha_fin=date.today())
        UsuarioCargo.objects.create(
            usuario=self.admin,
            cargo=Cargo.objects.get_or_create(nombre='funcionario')[0],
        )
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='access_admin_users',
        )
        role = Rol.objects.create(nombre='Administrar usuarios')
        ensure_role_group(role).permissions.add(permission)
        self.admin.roles.add(role)
        self.client.force_login(self.admin)

        response = self.client.post(reverse('administracion:home'), {
            'action': 'cambiar_estado',
            'usuario_id': target.pk,
        }, follow=True)
        self.assertContains(response, 'último Administrador')
        target.refresh_from_db()
        self.assertTrue(target.is_active)

        response = self.client.post(reverse('administracion:home'), {
            'action': 'eliminar',
            'usuario_id': target.pk,
        }, follow=True)
        self.assertContains(response, 'último Administrador')
        self.assertTrue(get_user_model().objects.filter(pk=target.pk).exists())

        response = self.client.post(reverse('administracion:home'), {
            'usuario_id': target.pk,
            'email': target.email,
            'first_name': '',
            'last_name': '',
            'delegacion': '',
            'delegaciones_autorizadas': [],
            'cargo': self.admin.cargo_id,
            'roles': [],
            'is_active': 'on',
            'password1': '',
            'password2': '',
        })
        self.assertRedirects(response, reverse('administracion:home'))
        target.refresh_from_db()
        self.assertEqual(target.cargo_id, admin_cargo.pk)

        with self.assertRaises(ValidationError):
            get_user_model().objects.filter(pk=target.pk).update(
                is_active=False,
            )
        UsuarioCargo.objects.filter(
            usuario=target,
            fecha_fin__isnull=True,
        ).update(fecha_fin=date.today())
        UsuarioCargo.objects.create(
            usuario=target,
            cargo=self.admin.cargo,
        )
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                target.save()
        target.refresh_from_db()
        self.assertEqual(target.cargo_id, admin_cargo.pk)

        response = self.client.get(
            reverse('administracion:home'),
            {'editar': target.pk},
        )
        self.assertContains(response, 'Último Administrador activo protegido')
        self.assertContains(response, 'disabled')

    def test_type_cannot_be_deleted_while_subtypes_are_associated(self):
        attention_type = Tipo.objects.create(
            nombre='Orientación',
        )
        Subtipo.objects.create(
            nombre='Social',
            tipo=attention_type,
        )

        response = self.client.post(reverse('administracion:tipos-atencion'), {
            'action': 'eliminar',
            'object_id': attention_type.pk,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('administracion:tipos-atencion'))
        self.assertTrue(Tipo.objects.filter(pk=attention_type.pk).exists())
        self.assertContains(
            self.client.get(reverse('administracion:tipos-atencion')),
            'El tipo tiene subatenciones asociadas',
        )

    def test_item_and_meta_assignment_crud_preserves_progress(self):
        function = Funcion.objects.create(nombre='Atención territorial')
        item = Item.objects.create(
            nombre='Orientaciones',
            descripcion='Atenciones registradas',
        )
        self.assertEqual(item.codigo, f'ITEM-{item.pk:04d}')
        user = create_user(
            email='persona-meta@sgr.test',
            password='Sgr-Test-Password-418!',
            first_name='Ana',
        )
        period = Periodo.objects.create(
            nombre='Período de metas',
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=30),
        )

        response = self.client.post(reverse('administracion:metas'), {
            'action': 'guardar',
            'usuario': user.pk,
            'item': item.pk,
            'periodo': period.pk,
            'meta': '12.00',
            'ponderacion': '50.00',
        })

        self.assertRedirects(response, reverse('administracion:metas'))
        goal = Desempeno.objects.get(usuario=user, item=item, periodo=period)
        self.assertEqual(goal.item, item)
        goal.avance = 2
        goal.save(update_fields=['avance'])

        response = self.client.post(reverse('administracion:metas'), {
            'action': 'eliminar',
            'object_id': goal.pk,
        })
        self.assertRedirects(response, reverse('administracion:metas'))
        self.assertTrue(Desempeno.objects.filter(pk=goal.pk).exists())

    def test_user_editor_assigns_authorized_delegations_and_can_export(self):
        primary = Delegacion.objects.create(nombre='Delegación Principal')
        authorized = Delegacion.objects.create(nombre='Delegación Autorizada')
        response = self.client.post(reverse('administracion:home'), {
            'email': 'persona-delegada@sgr.test',
            'nombre': 'María Prueba',
            'first_name': 'María',
            'last_name': 'Prueba',
            'cargo': Cargo.objects.get(nombre='administrador').pk,
            'delegacion': primary.pk,
            'delegaciones_autorizadas': [authorized.pk],
            'password1': 'Sgr-New-Account-573!',
            'password2': 'Sgr-New-Account-573!',
            'estado': 'activo',
            'is_active': 'on',
        })
        self.assertRedirects(response, reverse('administracion:home'))
        user = get_user_model().objects.get(email='persona-delegada@sgr.test')
        self.assertSetEqual(
            set(user.delegaciones_autorizadas.values_list('pk', flat=True)),
            {primary.pk, authorized.pk},
        )

        excel = self.client.get(
            reverse('administracion:home'),
            {'q': 'persona-delegada', 'export': 'excel'},
        )
        workbook = load_workbook(BytesIO(excel.content), read_only=True)
        worksheet = workbook.active
        self.assertEqual(worksheet.max_row, 2)
        self.assertEqual(worksheet.cell(1, 1).value, 'Correo electrónico')
        self.assertNotIn(
            'password',
            [cell.value for cell in worksheet[1]],
        )

    def test_user_without_delegation_can_open_editor_and_assign_one(self):
        employee = create_user(
            email='sin-delegacion@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        delegation = Delegacion.objects.create(
            nombre='Delegación para asignación',
            estado=Delegacion.Estado.ACTIVA,
        )

        response = self.client.get(
            reverse('administracion:home'),
            {'editar': employee.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delegación para asignación')

        response = self.client.post(reverse('administracion:home'), {
            'usuario_id': employee.pk,
            'email': employee.email,
            'first_name': 'Funcionario',
            'last_name': 'Sin delegación',
            'nombre': 'Funcionario sin delegación',
            'cargo': UsuarioCargo.objects.get(
                usuario=employee,
                fecha_fin__isnull=True,
            ).cargo_id,
            'delegacion': delegation.pk,
            'delegaciones_autorizadas': [delegation.pk],
            'password1': '',
            'password2': '',
            'estado': employee.estado,
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('administracion:home'))
        employee.refresh_from_db()
        self.assertEqual(employee.delegacion_id, delegation.pk)
        self.assertQuerySetEqual(
            employee.delegaciones_autorizadas.order_by('pk'),
            [delegation],
        )

    def test_inactive_delegations_cannot_be_assigned_or_selected(self):
        active = Delegacion.objects.create(nombre='Delegación vigente')
        inactive = Delegacion.objects.create(
            nombre='Delegación desactivada',
            estado=Delegacion.Estado.INACTIVA,
        )
        managed_user = create_user(
            email='cuenta-contexto@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.get(nombre='administrador'),
            delegacion=active,
        )
        UsuarioDelegacion.objects.create(
            usuario=managed_user,
            delegacion=inactive,
        )
        self.assertEqual(
            list(authorized_delegations(managed_user)),
            [active],
        )

        response = self.client.post(reverse('administracion:home'), {
            'email': 'cuenta-nueva@sgr.test',
            'first_name': 'Cuenta',
            'last_name': 'Prueba',
            'delegacion': inactive.pk,
            'delegaciones_autorizadas': [inactive.pk],
            'password1': 'Sgr-New-Account-573!',
            'password2': 'Sgr-New-Account-573!',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(email='cuenta-nueva@sgr.test').exists()
        )
        self.assertTrue(
            managed_user.delegaciones_autorizadas.filter(pk=inactive.pk).exists()
        )

    def test_search_and_status_filters_are_preserved_in_pagination(self):
        for index in range(52):
            Delegacion.objects.create(
                codigo=f'NORTE-{index:02d}',
                nombre=f'Norte {index:02d}',
                estado=(
                    Delegacion.Estado.ACTIVA
                    if index % 2 == 0 else Delegacion.Estado.INACTIVA
                ),
            )

        response = self.client.get(
            reverse('administracion:delegaciones'),
            {'q': 'Norte', 'estado': 'activa', 'page': '2'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 26)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertIn('q=Norte', response.context['pagination_query'])
        self.assertIn('estado=activa', response.context['pagination_query'])

    def test_excel_export_contains_all_filtered_rows_and_escapes_formulas(self):
        Delegacion.objects.create(
            codigo='EXP-001',
            nombre='=HYPERLINK("https://example.invalid")',
            estado=Delegacion.Estado.ACTIVA,
        )
        Delegacion.objects.create(
            codigo='EXP-002',
            nombre='No incluir',
            estado=Delegacion.Estado.INACTIVA,
        )

        response = self.client.get(
            reverse('administracion:delegaciones'),
            {'estado': 'activa', 'export': 'excel'},
        )

        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        rows = list(workbook.active.values)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], '\'=HYPERLINK("https://example.invalid")')

    def test_coordinator_can_manage_items_but_not_administration_roles(self):
        coordinator = create_user(
            email='coordinador-maintainers@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
        )
        self.client.force_login(coordinator)

        self.assertEqual(
            self.client.get(reverse('administracion:items')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('administracion:roles')).status_code,
            403,
        )

    def test_coordinator_cannot_view_or_edit_goals_outside_active_delegation(self):
        assigned = Delegacion.objects.create(nombre='Delegación asignada')
        other = Delegacion.objects.create(nombre='Delegación ajena')
        coordinator = create_user(
            email='coordinador-scope@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
            delegacion=assigned,
        )
        other_user = create_user(
            email='usuario-otra-delegacion@sgr.test',
            password='Sgr-Test-Password-418!',
            delegacion=other,
        )
        function = Funcion.objects.create(nombre='Función acotada')
        item = Item.objects.create(nombre='Meta restringida')
        period = Periodo.objects.create(
            nombre='Período acotado',
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=30),
        )
        goal = Desempeno.objects.create(
            usuario=other_user,
            item=item,
            periodo=period,
            meta=10,
        )
        self.client.force_login(coordinator)

        listing = self.client.get(reverse('administracion:metas'))
        edit = self.client.get(
            reverse('administracion:metas'),
            {'editar': goal.pk},
        )
        delete = self.client.post(reverse('administracion:metas'), {
            'action': 'eliminar',
            'object_id': goal.pk,
        })

        self.assertNotContains(listing, other_user.email)
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertTrue(Desempeno.objects.filter(pk=goal.pk).exists())
