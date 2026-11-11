import csv
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate
from django.http import Http404
from django.test import Client, RequestFactory, TestCase
from django.urls import resolve, reverse

from AdminApp.templatetags.navigation_tags import SIDEBAR_SECTIONS
from AdminApp.csv_utils import csv_response
from AdminApp.delegation_scope import filter_by_delegation
from AdminApp.models import Cargo, Delegacion, Historial, ParametroSistema, Rol, UsuarioRol
from AdminApp.roles import role_group_name
from AdminApp.signals import provision_catalog_permissions
from config.permissions import PERMISSION_CATALOG, can_access_permission
from CoordinadorApp.services import max_dias_autorizacion
from test_helpers import create_user


class PermissionCatalogProvisioningTests(TestCase):
    def test_post_migrate_provisions_all_catalog_permissions_idempotently(self):
        content_type = ContentType.objects.get_for_model(Rol)
        codenames = {definition.codename for definition in PERMISSION_CATALOG}
        Permission.objects.filter(
            content_type=content_type,
            codename__in=codenames,
        ).delete()
        app_config = next(
            config for config in apps.get_app_configs()
            if config.name == 'AdminApp'
        )
        signal_args = {
            'app_config': app_config,
            'verbosity': 0,
            'interactive': False,
            'using': 'default',
            'apps': apps,
            'plan': [],
        }

        post_migrate.send(sender=app_config, **signal_args)
        post_migrate.send(sender=app_config, **signal_args)

        provisioned = Permission.objects.filter(
            content_type=content_type,
            codename__in=codenames,
        )
        self.assertSetEqual(
            set(provisioned.values_list('codename', flat=True)),
            codenames,
        )
        self.assertEqual(provisioned.count(), len(codenames))


class RoleSignalTests(TestCase):
    def test_saving_role_synchronizes_active_usuario_rol_assignments(self):
        role = Rol.objects.create(nombre='Permiso sincronizado')
        user = get_user_model().objects.create_user(
            email='rol-signal@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        UsuarioRol.objects.create(usuario=user, rol=role)

        role.nombre = 'Permiso sincronizado actualizado'
        role.save()

        self.assertTrue(
            user.groups.filter(name=role_group_name(role)).exists(),
        )

        role.estado = Rol.Estado.INACTIVO
        role.save()
        self.assertFalse(
            user.groups.filter(name=role_group_name(role)).exists(),
        )


class AuthorizationParameterTests(TestCase):
    def test_authorization_days_use_code_default_without_database_row(self):
        ParametroSistema.objects.filter(
            clave=ParametroSistema.Clave.MAX_DIAS_AUTORIZACION,
        ).delete()

        self.assertEqual(max_dias_autorizacion(), 7)


class DelegationScopeTests(TestCase):
    def setUp(self):
        self.first_delegation = Delegacion.objects.create(
            nombre='Delegación uno',
        )
        self.second_delegation = Delegacion.objects.create(
            nombre='Delegación dos',
        )
        self.admin = create_user(
            email='scope-admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        self.employee = create_user(
            email='scope-employee@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
            delegacion=self.first_delegation,
        )
        self.factory = RequestFactory()

    def test_only_administrator_can_select_all_delegations(self):
        all_request = self.factory.get('/admin-app/?delegacion=todas')
        all_request.user = self.admin
        all_request.session = {}
        self.assertCountEqual(
            filter_by_delegation(
                Delegacion.objects.all(),
                all_request,
                delegation_lookup='pk',
            ),
            [self.first_delegation, self.second_delegation],
        )

        forbidden_request = self.factory.get('/admin-app/?delegacion=todas')
        forbidden_request.user = self.employee
        forbidden_request.session = {}
        with self.assertRaises(Http404):
            filter_by_delegation(
                Delegacion.objects.all(),
                forbidden_request,
                delegation_lookup='pk',
            )

    def test_selected_delegation_is_authorized_and_rechecked(self):
        request = self.factory.get(
            f'/admin-app/?delegacion={self.second_delegation.pk}',
        )
        request.user = self.admin
        request.session = {}
        scoped = filter_by_delegation(
            Delegacion.objects.all(),
            request,
            delegation_lookup='pk',
        )
        self.assertEqual(list(scoped), [self.second_delegation])

        forbidden_request = self.factory.get(
            f'/admin-app/?delegacion={self.second_delegation.pk}',
        )
        forbidden_request.user = self.employee
        forbidden_request.session = {}
        with self.assertRaises(Http404):
            filter_by_delegation(
                Delegacion.objects.all(),
                forbidden_request,
                delegation_lookup='pk',
            )


class PermissionAndCsvTests(TestCase):
    def test_every_catalog_permission_maps_to_a_protected_route(self):
        for definition in PERMISSION_CATALOG:
            with self.subTest(view=definition.view_name):
                view = resolve(reverse(
                    definition.view_name,
                    kwargs=dict(definition.route_kwargs),
                )).func
                self.assertEqual(
                    view.required_permission,
                    definition.codename,
                )

    def test_non_administrator_access_depends_on_catalog_permission(self):
        user = get_user_model().objects.create_user(
            email='catalog-viewer@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='access_admin_absences',
        )
        user.user_permissions.add(permission)

        self.assertTrue(
            can_access_permission(
                user,
                'access_admin_absences',
                ('admin', 'administrador'),
            ),
        )
        user.user_permissions.remove(permission)
        user = get_user_model().objects.get(pk=user.pk)
        self.assertFalse(
            can_access_permission(
                user,
                'access_admin_absences',
                ('admin', 'administrador'),
            ),
        )

    def test_csv_normalizes_leading_whitespace_and_audits_export(self):
        user = get_user_model().objects.create_user(
            email='csv-exporter@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        request = RequestFactory().get('/admin-app/?q=buscar')
        request.user = user

        response = csv_response(
            request,
            filename='exportacion.csv',
            rows=[['Dato'], ['  =formula'], ['\t+formula'], ['-formula'], ['@formula']],
            entity='PruebaExportacion',
            filters={'q': 'buscar'},
            row_count=4,
        )

        content = response.content.decode('utf-8-sig')
        rows = list(csv.reader(StringIO(content)))
        self.assertEqual(
            [row[0] for row in rows[1:]],
            ["'=formula", "'+formula", "'-formula", "'@formula"],
        )
        history = Historial.objects.get(entidad_afectada='PruebaExportacion')
        self.assertEqual(history.accion, 'Exportar CSV')
        self.assertEqual(history.valor_nuevo['filas'], 4)

    def test_administrator_navigation_uses_the_required_groups_without_empty_links(self):
        admin = create_user(
            email='sidebar-admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        client = Client()
        client.force_login(admin)

        response = client.get(reverse('administracion:home'))

        self.assertEqual(response.status_code, 200)
        section_labels = {label for _, label, _ in SIDEBAR_SECTIONS}
        self.assertTrue({
            'Organización',
            'Territorio',
            'Operación',
            'Metas y seguimiento',
            'Informes',
            'Auditoría',
        }.issubset(section_labels))
        for route_name in (
            'administracion:ausencias',
            'administracion:felicitaciones',
            'administracion:reclamos',
            'administracion:hitos',
            'administracion:vecinos',
            'administracion:juntas',
            'administracion:informes-generados',
            'administracion:resumen-delegacion',
            'administracion:registros',
            'administracion:atenciones-sociales',
            'administracion:compromisos',
            'administracion:ajustes-metas',
        ):
            self.assertContains(response, reverse(route_name))
        for route_name in (
            'administracion:metas',
            'administracion:funciones',
            'coordinador:ponderaciones',
        ):
            self.assertContains(response, reverse(route_name))

    def test_administrator_dashboard_is_separate_from_user_management(self):
        admin = create_user(
            email='dashboard-admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        client = Client()
        client.force_login(admin)

        response = client.get(reverse('administracion:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Panel de Administración')
        self.assertContains(response, 'Accesos rápidos')
        self.assertContains(response, 'Usuarios activos')
        self.assertContains(response, 'data-current="true"')
        self.assertNotContains(response, 'Crear usuario')

        response = client.get(reverse('administracion:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Administración de usuarios')
        self.assertContains(response, 'Crear usuario')

    def test_non_administrator_cannot_open_administrator_dashboard(self):
        user = create_user(
            email='dashboard-funcionario@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse('administracion:dashboard'))

        self.assertEqual(response.status_code, 403)

    def test_home_redirect_sends_administrator_to_dashboard(self):
        admin = create_user(
            email='dashboard-redirect@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='admin'),
        )
        client = Client()
        client.force_login(admin)

        response = client.get(reverse('home'))

        self.assertRedirects(response, reverse('administracion:dashboard'))
