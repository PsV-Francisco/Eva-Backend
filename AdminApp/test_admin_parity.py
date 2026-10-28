from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from AdminApp.models import (
    Cargo,
    Catalogo,
    Historial,
    PasswordResetAuditEvent,
    is_critical_cargo_name,
)
from CoordinadorApp.models import CargoFuncion, Funcion, Item, Periodo
from FuncionarioApp.models import Registro


class AdminParityMaintainerTests(TestCase):
    def setUp(self):
        admin_cargo, _ = Cargo.objects.get_or_create(nombre='administrador')
        self.admin = get_user_model().objects.create_superuser(
            email='parity-admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=admin_cargo,
        )
        self.client.force_login(self.admin)

    def post_maintainer(self, route_name, data):
        return self.client.post(
            reverse(f'administracion:{route_name}'),
            {'action': 'guardar', **data},
        )

    def test_cargo_crud_search_and_safe_deactivation(self):
        response = self.post_maintainer('cargos', {
            'nombre': 'Encargado territorial',
            'funciones': '',
            'estado': Cargo.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:cargos'))
        cargo = Cargo.objects.get(nombre='Encargado territorial')
        self.assertContains(
            self.client.get(reverse('administracion:cargos'), {'q': 'territorial'}),
            'Encargado territorial',
        )

        response = self.post_maintainer('cargos', {
            'object_id': cargo.pk,
            'nombre': 'Gestor territorial',
            'funciones': '',
            'estado': Cargo.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:cargos'))
        cargo.refresh_from_db()
        self.assertEqual(cargo.nombre, 'Gestor territorial')

        response = self.client.post(reverse('administracion:cargos'), {
            'action': 'cambiar_estado',
            'object_id': cargo.pk,
        })
        self.assertRedirects(response, reverse('administracion:cargos'))
        cargo.refresh_from_db()
        self.assertEqual(cargo.estado, Cargo.Estado.INACTIVO)

        response = self.client.post(reverse('administracion:cargos'), {
            'action': 'eliminar',
            'object_id': cargo.pk,
        })
        self.assertRedirects(response, reverse('administracion:cargos'))
        self.assertFalse(Cargo.objects.filter(pk=cargo.pk).exists())

    def test_cargo_with_users_cannot_be_deleted(self):
        cargo = Cargo.objects.create(nombre='Cargo con usuario')
        get_user_model().objects.create_user(
            email='cargo-user@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=cargo,
        )

        response = self.client.post(
            reverse('administracion:cargos'),
            {'action': 'eliminar', 'object_id': cargo.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Cargo.objects.filter(pk=cargo.pk).exists())
        self.assertContains(response, 'tiene usuarios o asignaciones asociadas')

    def test_access_control_cargos_cannot_be_renamed_or_deleted(self):
        protected_names = (
            'admin',
            'administrador',
            'supervisor',
            'coordinador',
            'delegado',
            'funcionario',
            'verificador',
            'vistaf',
            'consulta',
            'usuario de consulta',
        )
        for index, name in enumerate(protected_names):
            with self.subTest(cargo=name):
                cargo, _ = Cargo.objects.get_or_create(nombre=name)
                cargo.nombre = f'{name} modificado'
                with self.assertRaises(ValidationError):
                    cargo.save()
                cargo.refresh_from_db()
                with self.assertRaises(ProtectedError):
                    cargo.delete()
                with self.assertRaises(ProtectedError):
                    Cargo.objects.filter(pk=cargo.pk).delete()

                response = self.client.post(reverse('administracion:cargos'), {
                    'action': 'guardar',
                    'object_id': cargo.pk,
                    'nombre': f'{name} editado {index}',
                    'funciones': '',
                    'estado': Cargo.Estado.ACTIVO,
                })
                self.assertEqual(response.status_code, 200)
                cargo.refresh_from_db()
                self.assertEqual(cargo.nombre, name)
                response = self.client.post(reverse('administracion:cargos'), {
                    'action': 'eliminar',
                    'object_id': cargo.pk,
                })
                self.assertRedirects(response, reverse('administracion:cargos'))
                self.assertTrue(Cargo.objects.filter(pk=cargo.pk).exists())

        self.assertTrue(is_critical_cargo_name(' Administrador '))

    def test_function_crud_and_safe_deactivation(self):
        response = self.post_maintainer('funciones', {
            'nombre': 'Atención comunitaria',
            'descripcion': 'Primera versión',
            'estado': Funcion.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:funciones'))
        function = Funcion.objects.get(nombre='Atención comunitaria')
        self.assertContains(
            self.client.get(reverse('administracion:funciones'), {'q': 'comunitaria'}),
            'Atención comunitaria',
        )

        response = self.post_maintainer('funciones', {
            'object_id': function.pk,
            'nombre': 'Gestión comunitaria',
            'descripcion': 'Actualizada',
            'estado': Funcion.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:funciones'))
        function.refresh_from_db()
        self.assertEqual(function.nombre, 'Gestión comunitaria')

        response = self.client.post(reverse('administracion:funciones'), {
            'action': 'cambiar_estado',
            'object_id': function.pk,
        })
        self.assertRedirects(response, reverse('administracion:funciones'))
        function.refresh_from_db()
        self.assertEqual(function.estado, Funcion.Estado.INACTIVO)

        response = self.client.post(reverse('administracion:funciones'), {
            'action': 'eliminar',
            'object_id': function.pk,
        })
        self.assertRedirects(response, reverse('administracion:funciones'))
        self.assertFalse(Funcion.objects.filter(pk=function.pk).exists())

    def test_function_with_items_cannot_be_deleted(self):
        function = Funcion.objects.create(nombre='Función con ítem')
        Item.objects.create(funcion=function, nombre='Ítem asociado')

        response = self.client.post(
            reverse('administracion:funciones'),
            {'action': 'eliminar', 'object_id': function.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Funcion.objects.filter(pk=function.pk).exists())
        self.assertContains(response, 'tiene ítems o cargos asociados')

    def test_cargo_function_assignment_crud(self):
        cargo = Cargo.objects.create(nombre='Cargo asignable')
        function = Funcion.objects.create(nombre='Función asignable')
        replacement = Funcion.objects.create(nombre='Función alternativa')

        response = self.post_maintainer('cargos-funciones', {
            'cargo': cargo.pk,
            'funcion': function.pk,
        })
        self.assertRedirects(
            response,
            reverse('administracion:cargos-funciones'),
        )
        assignment = CargoFuncion.objects.get(cargo=cargo, funcion=function)
        self.assertContains(
            self.client.get(
                reverse('administracion:cargos-funciones'),
                {'q': 'asignable'},
            ),
            'Cargo asignable',
        )

        response = self.post_maintainer('cargos-funciones', {
            'object_id': assignment.pk,
            'cargo': cargo.pk,
            'funcion': replacement.pk,
        })
        self.assertRedirects(
            response,
            reverse('administracion:cargos-funciones'),
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.funcion, replacement)

        response = self.client.post(
            reverse('administracion:cargos-funciones'),
            {'action': 'eliminar', 'object_id': assignment.pk},
        )
        self.assertRedirects(
            response,
            reverse('administracion:cargos-funciones'),
        )
        self.assertFalse(CargoFuncion.objects.filter(pk=assignment.pk).exists())

    def test_catalog_crud_and_referenced_entries_are_preserved(self):
        response = self.post_maintainer('catalogo', {
            'actividad': 'Actividad vecinal',
            'servicio': 'Orientación',
            'tipo': 'Social',
            'subtipo': 'General',
            'estado': Catalogo.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:catalogo'))
        catalog = Catalogo.objects.get(actividad='Actividad vecinal')
        self.assertContains(
            self.client.get(reverse('administracion:catalogo'), {'q': 'vecinal'}),
            'Actividad vecinal',
        )

        response = self.post_maintainer('catalogo', {
            'object_id': catalog.pk,
            'actividad': 'Actividad comunitaria',
            'servicio': 'Orientación',
            'tipo': 'Social',
            'subtipo': 'General',
            'estado': Catalogo.Estado.ACTIVO,
        })
        self.assertRedirects(response, reverse('administracion:catalogo'))
        catalog.refresh_from_db()
        self.assertEqual(catalog.actividad, 'Actividad comunitaria')

        function = Funcion.objects.create(nombre='Función de registro')
        item = Item.objects.create(funcion=function, nombre='Ítem de registro')
        period = Periodo.objects.create(
            nombre='Período catálogo',
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=7),
        )
        employee_cargo = Cargo.objects.create(nombre='funcionario')
        employee = get_user_model().objects.create_user(
            email='catalog-record@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
        )
        Registro.objects.create(
            fecha=date.today(),
            periodo=period,
            item=item,
            catalogo=catalog,
            descripcion='Registro histórico',
            autor=employee,
        )

        response = self.client.post(
            reverse('administracion:catalogo'),
            {'action': 'eliminar', 'object_id': catalog.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        catalog.refresh_from_db()
        self.assertEqual(catalog.estado, Catalogo.Estado.ACTIVO)
        self.assertTrue(Registro.objects.filter(catalogo=catalog).exists())
        self.assertContains(response, 'tiene actividades asociadas')

        response = self.client.post(reverse('administracion:catalogo'), {
            'action': 'cambiar_estado',
            'object_id': catalog.pk,
        })
        self.assertRedirects(response, reverse('administracion:catalogo'))
        catalog.refresh_from_db()
        self.assertEqual(catalog.estado, Catalogo.Estado.INACTIVO)

    def test_audit_viewers_filter_and_reject_mutations(self):
        Historial.objects.create(
            autor=self.admin,
            accion='Actualizar cargo',
            entidad_afectada='Cargo:25',
            valor_anterior={'nombre': 'Anterior'},
            valor_nuevo={'nombre': 'Nuevo'},
        )
        event = PasswordResetAuditEvent.objects.create(
            user=self.admin,
            action=PasswordResetAuditEvent.Action.REQUEST,
            email_fingerprint='f' * 64,
            ip_address='192.0.2.10',
            was_rate_limited=True,
        )

        history_response = self.client.get(
            reverse('administracion:historial'),
            {'q': 'Cargo:25', 'accion': 'Actualizar cargo'},
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertContains(history_response, 'Actualizar cargo')
        self.assertContains(history_response, 'Anterior')
        self.assertEqual(
            self.client.post(reverse('administracion:historial')).status_code,
            405,
        )
        self.assertTrue(Historial.objects.filter(accion='Actualizar cargo').exists())

        audit_response = self.client.get(
            reverse('administracion:auditoria-recuperacion'),
            {'accion': PasswordResetAuditEvent.Action.REQUEST, 'limitada': 'si'},
        )
        self.assertEqual(audit_response.status_code, 200)
        self.assertContains(audit_response, self.admin.email)
        self.assertEqual(
            self.client.post(
                reverse('administracion:auditoria-recuperacion'),
            ).status_code,
            405,
        )
        event.refresh_from_db()
        self.assertTrue(event.was_rate_limited)

    def test_new_admin_routes_deny_non_administrator_cargos(self):
        employee = get_user_model().objects.create_user(
            email='parity-employee@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.client.force_login(employee)
        route_names = (
            'cargos',
            'funciones',
            'cargos-funciones',
            'catalogo',
            'historial',
            'auditoria-recuperacion',
        )
        for route_name in route_names:
            with self.subTest(route=route_name):
                self.assertEqual(
                    self.client.get(
                        reverse(f'administracion:{route_name}'),
                    ).status_code,
                    403,
                )
