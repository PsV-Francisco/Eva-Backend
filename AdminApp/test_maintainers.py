from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from AdminApp.models import (
    Cargo,
    Delegacion,
    Historial,
    Rol,
    SubAtencion,
    TipoAtencion,
)
from CoordinadorApp.models import Desempeno, Funcion, Item, Periodo
from config.delegations import authorized_delegations


class MaintainerTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            email='admin-maintainers@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
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

    def test_non_administrator_cannot_open_administration_routes(self):
        user = get_user_model().objects.create_user(
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
        response = self.client.post(reverse('administracion:roles'), {
            'action': 'guardar',
            'nombre': 'Coordinador Territorial',
            'descripcion': 'Gestión de una delegación',
            'permisos': 'items.manage',
            'alcance': Rol.Alcance.DELEGACION,
            'estado': Rol.Estado.ACTIVO,
        })

        self.assertRedirects(response, reverse('administracion:roles'))
        role = Rol.objects.get(nombre='Coordinador Territorial')
        self.assertEqual(role.permisos, 'items.manage')
        self.assertEqual(role.alcance, Rol.Alcance.DELEGACION)
        self.assertEqual(role.descripcion, 'Gestión de una delegación')

    def test_type_cannot_be_deleted_while_subtypes_are_associated(self):
        attention_type = TipoAtencion.objects.create(
            codigo='TAT-001',
            nombre='Orientación',
        )
        SubAtencion.objects.create(
            codigo='SAT-001',
            nombre='Social',
            tipo_atencion=attention_type,
        )

        response = self.client.post(reverse('administracion:tipos-atencion'), {
            'action': 'eliminar',
            'object_id': attention_type.pk,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('administracion:tipos-atencion'))
        self.assertTrue(TipoAtencion.objects.filter(pk=attention_type.pk).exists())
        self.assertContains(
            self.client.get(reverse('administracion:tipos-atencion')),
            'El tipo tiene subatenciones asociadas',
        )

    def test_item_and_meta_assignment_crud_preserves_progress(self):
        function = Funcion.objects.create(nombre='Atención territorial')
        item = Item.objects.create(
            funcion=function,
            nombre='Orientaciones',
            descripcion='Atenciones registradas',
        )
        self.assertEqual(item.codigo, f'ITEM-{item.pk:04d}')
        user = get_user_model().objects.create_user(
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
        self.assertEqual(goal.funcion, function)
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
            'first_name': 'María',
            'last_name': 'Prueba',
            'delegacion': primary.pk,
            'delegaciones_autorizadas': [authorized.pk],
            'password1': 'Sgr-New-Account-573!',
            'password2': 'Sgr-New-Account-573!',
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

    def test_inactive_delegations_cannot_be_assigned_or_selected(self):
        active = Delegacion.objects.create(nombre='Delegación vigente')
        inactive = Delegacion.objects.create(
            nombre='Delegación desactivada',
            estado=Delegacion.Estado.INACTIVA,
        )
        managed_user = get_user_model().objects.create_user(
            email='cuenta-contexto@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.get(nombre='administrador'),
            delegacion=active,
        )
        managed_user.delegaciones_autorizadas.add(inactive)
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
        coordinator = get_user_model().objects.create_user(
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
        coordinator = get_user_model().objects.create_user(
            email='coordinador-scope@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
            delegacion=assigned,
        )
        other_user = get_user_model().objects.create_user(
            email='usuario-otra-delegacion@sgr.test',
            password='Sgr-Test-Password-418!',
            delegacion=other,
        )
        function = Funcion.objects.create(nombre='Función acotada')
        item = Item.objects.create(funcion=function, nombre='Meta restringida')
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
            ponderacion=50,
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
