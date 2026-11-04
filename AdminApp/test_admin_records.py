from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from AdminApp.models import Cargo, Delegacion, Historial
from CoordinadorApp.models import (
    AtencionSocial,
    Desempeno,
    GestionAtencion,
    Item,
    Periodo,
)
from DelegadoApp.models import (
    Agenda,
    Ausencia,
    Compromiso,
    Felicitacion,
    Hito,
    Informe,
    Reclamo,
)
from FuncionarioApp.models import (
    Beneficiado,
    CargoJv,
    JuntaVecino,
    Registro,
    Subtipo,
    Territorio,
    Tipo,
    Vecino,
)
from test_helpers import create_user


class AdministratorRecordScreensTests(TestCase):
    def setUp(self):
        self.first_delegation = Delegacion.objects.create(
            nombre='Delegación records norte',
        )
        self.second_delegation = Delegacion.objects.create(
            nombre='Delegación records sur',
        )
        self.admin = create_user(
            email='records-admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        employee_cargo, _ = Cargo.objects.get_or_create(nombre='funcionario')
        self.employee = create_user(
            email='records-employee@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
            delegacion=self.first_delegation,
        )
        self.second_employee = create_user(
            email='records-second-employee@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
            delegacion=self.second_delegation,
        )
        self.period = Periodo.objects.create(
            nombre='Período de listados',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
        self.item = Item.objects.create(nombre='Ítem de listados')
        self.first_performance = Desempeno.objects.create(
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
            meta=10,
        )
        self.second_performance = Desempeno.objects.create(
            usuario=self.second_employee,
            item=self.item,
            periodo=self.period,
            meta=10,
        )
        self.client = Client()

    def test_all_read_only_screen_routes_render_for_administrator(self):
        self.client.force_login(self.admin)
        route_names = (
            'administracion:ausencias',
            'administracion:felicitaciones',
            'administracion:reclamos',
            'administracion:hitos',
        )

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Exportar CSV')
                self.assertContains(response, 'Todas las delegaciones')

    def test_permission_and_delegation_scope_are_enforced_on_list_view(self):
        first_record = Ausencia.objects.create(
            fecha='2026-03-01T10:00:00Z',
            descripcion='Dato de primera delegación',
            desempeno=self.first_performance,
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
        )
        second_record = Ausencia.objects.create(
            fecha='2026-03-02T10:00:00Z',
            descripcion='Dato de segunda delegación',
            desempeno=self.second_performance,
            usuario=self.second_employee,
            item=self.item,
            periodo=self.period,
        )
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename='access_admin_absences',
        )
        self.employee.user_permissions.add(permission)
        self.client.force_login(self.employee)

        response = self.client.get(reverse('administracion:ausencias'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first_record.descripcion)
        self.assertNotContains(response, second_record.descripcion)
        self.assertEqual(
            self.client.get(
                reverse('administracion:ausencias'),
                {'delegacion': self.second_delegation.pk},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('administracion:ausencias'),
                {'delegacion': 'todas'},
            ).status_code,
            404,
        )

        user_without_permission = create_user(
            email='records-no-permission@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.get(nombre='funcionario'),
            delegacion=self.first_delegation,
        )
        self.client.force_login(user_without_permission)
        self.assertEqual(
            self.client.get(reverse('administracion:ausencias')).status_code,
            403,
        )

    def test_administrator_filter_applies_before_csv_export_and_audits_it(self):
        Ausencia.objects.create(
            fecha='2026-03-01T10:00:00Z',
            descripcion='Exportar esta ausencia',
            desempeno=self.first_performance,
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
        )
        Ausencia.objects.create(
            fecha='2026-03-02T10:00:00Z',
            descripcion='No exportar la otra ausencia',
            desempeno=self.second_performance,
            usuario=self.second_employee,
            item=self.item,
            periodo=self.period,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('administracion:ausencias'),
            {
                'delegacion': self.first_delegation.pk,
                'export': 'csv',
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        self.assertIn('Exportar esta ausencia', content)
        self.assertNotIn('No exportar la otra ausencia', content)
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Exportar CSV',
                entidad_afectada='Listado:ausencias',
            ).exists(),
        )

    def test_neighbor_and_junta_crud_reuses_employee_forms_and_revalidates_ids(self):
        territory = Territorio.objects.create(
            nombre='Territorio editable',
            delegacion=self.first_delegation,
        )
        junta = JuntaVecino.objects.create(
            nombre='Junta editable',
            domicilio_legal='Domicilio de prueba',
            numero_rpj=801,
            territorio=territory,
            delegacion=self.first_delegation,
        )
        cargo = CargoJv.objects.create(
            nombre='Tesorero',
            permisos='Administrar fondos',
            junta_vecino=junta,
        )
        vecino = Vecino.objects.create(
            nombre='Vecina editable',
            telefono='987654321',
            direccion='Calle de prueba',
            territorio=territory,
            delegacion=self.first_delegation,
            junta_vecino=junta,
            cargo_jv=cargo,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('administracion:vecinos'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, vecino.nombre)
        self.assertEqual(
            self.client.get(
                reverse('administracion:vecino-editar', args=[vecino.pk]),
                {'delegacion': self.second_delegation.pk},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('administracion:vecino-nuevo')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('administracion:junta-nueva')).status_code,
            200,
        )

        response = self.client.post(
            reverse('administracion:vecino-nuevo')
            + f'?delegacion={self.first_delegation.pk}',
            {
                'nombre': 'Vecino creado por administrador',
                'telefono': '912345678',
                'direccion': 'Nueva dirección',
                'delegacion': self.first_delegation.pk,
                'territorio': territory.pk,
                'junta_vecino': junta.pk,
                'cargo_jv': cargo.pk,
                'solicitante': '',
                'activo': 'on',
            },
        )
        self.assertRedirects(response, reverse('administracion:vecinos'))
        created_neighbor = Vecino.objects.get(
            nombre='Vecino creado por administrador',
        )
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Crear vecino',
                entidad_afectada=f'Vecino:{created_neighbor.pk}',
            ).exists(),
        )

        response = self.client.post(
            reverse(
                'administracion:junta-nueva',
            ) + f'?delegacion={self.first_delegation.pk}',
            {
                'nombre': 'Junta creada por administrador',
                'domicilio_legal': 'Domicilio nuevo',
                'socios_activos': '12',
                'fecha_constitucion': '',
                'numero_rpj': '802',
                'fecha_ingreso': '',
                'numero_registro': '',
                'delegacion': self.first_delegation.pk,
                'territorio': territory.pk,
            },
        )
        self.assertRedirects(response, reverse('administracion:juntas'))
        created_junta = JuntaVecino.objects.get(
            nombre='Junta creada por administrador',
        )
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Crear junta de vecinos',
                entidad_afectada=f'JuntaVecino:{created_junta.pk}',
            ).exists(),
        )

        response = self.client.post(
            reverse(
                'administracion:vecino-editar',
                args=[vecino.pk],
            ) + f'?delegacion={self.first_delegation.pk}',
            {
                'nombre': 'Vecina actualizada',
                'telefono': '987654321',
                'direccion': 'Calle actualizada',
                'delegacion': self.first_delegation.pk,
                'territorio': territory.pk,
                'junta_vecino': junta.pk,
                'cargo_jv': cargo.pk,
                'solicitante': '',
                'activo': 'on',
            },
        )
        self.assertRedirects(response, reverse('administracion:vecinos'))
        vecino.refresh_from_db()
        self.assertEqual(vecino.nombre, 'Vecina actualizada')
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Editar vecino',
                entidad_afectada=f'Vecino:{vecino.pk}',
            ).exists(),
        )

        response = self.client.post(
            reverse(
                'administracion:junta-editar',
                args=[created_junta.pk],
            ) + f'?delegacion={self.first_delegation.pk}',
            {
                'nombre': 'Junta actualizada',
                'domicilio_legal': 'Domicilio actualizado',
                'socios_activos': '14',
                'fecha_constitucion': '',
                'numero_rpj': '802',
                'fecha_ingreso': '',
                'numero_registro': '',
                'delegacion': self.first_delegation.pk,
                'territorio': territory.pk,
            },
        )
        self.assertRedirects(response, reverse('administracion:juntas'))
        created_junta.refresh_from_db()
        self.assertEqual(created_junta.nombre, 'Junta actualizada')

        response = self.client.post(
            reverse(
                'administracion:vecino-eliminar',
                args=[vecino.pk],
            ) + f'?delegacion={self.first_delegation.pk}',
        )
        self.assertRedirects(response, reverse('administracion:vecinos'))
        self.assertFalse(Vecino.objects.filter(pk=vecino.pk).exists())
        history = Historial.objects.filter(
            accion='Eliminar vecino',
        ).values('autor_id', 'accion', 'entidad_afectada')
        self.assertTrue(
            history.filter(
                autor=self.admin,
                entidad_afectada=f'Vecino:{vecino.pk}',
            ).exists(),
            list(history),
        )
        response = self.client.post(
            reverse(
            'administracion:junta-eliminar',
            args=[created_junta.pk],
            ) + f'?delegacion={self.first_delegation.pk}',
        )
        self.assertRedirects(response, reverse('administracion:juntas'))
        self.assertFalse(JuntaVecino.objects.filter(pk=created_junta.pk).exists())
        self.assertTrue(
            Historial.objects.filter(
            autor=self.admin,
            accion='Eliminar junta de vecinos',
            entidad_afectada=f'JuntaVecino:{created_junta.pk}',
            ).exists(),
        )

    def test_felicitations_complaints_and_milestones_list_records(self):
        Felicitacion.objects.create(
            evidencia='evidencia',
            fecha='2026-03-01',
            ubicacion='Plaza norte',
            estado='aprobada',
            desempeno=self.first_performance,
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
        )
        Reclamo.objects.create(
            evidencia='reclamo',
            fecha='2026-03-02T10:00:00Z',
            ubicacion='Plaza sur',
            estado='abierto',
            desempeno=self.first_performance,
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
        )
        territory = Territorio.objects.create(
            nombre='Territorio hito',
            delegacion=self.first_delegation,
        )
        tipo = Tipo.objects.create(nombre='Tipo hito')
        subtipo = Subtipo.objects.create(nombre='Subtipo hito', tipo=tipo)
        registro = Registro.objects.create(
            fecha='2026-03-03',
            item=self.item,
            periodo=self.period,
            descripcion='Registro asociado al hito',
            autor=self.employee,
            tipo=tipo,
            subtipo=subtipo,
        )
        Hito.objects.create(
            nombre='Hito territorial',
            descripcion='Descripción del hito',
            fecha_termino='2026-04-01T10:00:00Z',
            recursos_asociados=1,
            estado=Hito.Estado.ABIERTO,
            evento_recurrente=0,
            incluir_agenda=0,
            periocidad='único',
            territorio=territory,
            delegacion=self.first_delegation,
            responsable=self.employee,
            registro=registro,
            autor_registro=self.employee.pk,
            item_registro=self.item.pk,
            periodo_registro=self.period.pk,
        )
        self.client.force_login(self.admin)

        self.assertContains(
            self.client.get(reverse('administracion:felicitaciones')),
            'Plaza norte',
        )
        self.assertContains(
            self.client.get(reverse('administracion:reclamos')),
            'Plaza sur',
        )
        self.assertContains(
            self.client.get(reverse('administracion:hitos')),
            'Hito territorial',
        )

    def test_admin_reports_and_summary_cover_all_delegations_and_audit_exports(self):
        self.client.force_login(self.admin)

        report_response = self.client.get(
            reverse('administracion:informes-generados'),
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertContains(report_response, self.employee.email)
        self.assertContains(report_response, self.second_employee.email)

        export_response = self.client.get(
            reverse('administracion:informes-generados'),
            {'export': 'csv'},
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(self.employee.email, export_response.content.decode('utf-8-sig'))
        self.assertIn(
            self.second_employee.email,
            export_response.content.decode('utf-8-sig'),
        )
        generated = Informe.objects.get(autor=self.admin, formato='csv')
        self.assertEqual(generated.tipo, 'informe_consolidado')
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Exportar informe consolidado CSV',
            ).exists(),
        )

        summary_response = self.client.get(
            reverse('administracion:resumen-delegacion'),
        )
        self.assertEqual(summary_response.status_code, 200)
        self.assertContains(summary_response, 'Todas las delegaciones')
        self.assertContains(summary_response, self.employee.email)
        self.assertContains(summary_response, self.second_employee.email)
        scoped_summary = self.client.get(
            reverse('administracion:resumen-delegacion'),
            {'delegacion': self.first_delegation.pk},
        )
        self.assertContains(scoped_summary, self.employee.email)
        self.assertNotContains(scoped_summary, self.second_employee.email)
        summary_export = self.client.get(
            reverse('administracion:resumen-delegacion'),
            {'delegacion': 'todas', 'export': 'csv'},
        )
        self.assertEqual(summary_export.status_code, 200)
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                accion='Exportar resumen de delegación CSV',
            ).exists(),
        )

    def test_new_admin_screens_reject_non_admin_cargos(self):
        self.client.force_login(self.employee)
        route_names = (
            'administracion:informes-generados',
            'administracion:resumen-delegacion',
            'administracion:registros',
            'administracion:atenciones-sociales',
            'administracion:compromisos',
        )
        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertNotEqual(response.status_code, 200)

    def test_admin_read_only_lists_reuse_search_delegation_scope_and_audited_csv(self):
        tipo = Tipo.objects.create(nombre='Tipo registros de admin')
        subtipo = Subtipo.objects.create(
            nombre='Subtipo registros de admin',
            tipo=tipo,
        )
        first_record = Registro.objects.create(
            fecha='2026-03-01',
            item=self.item,
            periodo=self.period,
            descripcion='Registro visible norte',
            autor=self.employee,
            tipo=tipo,
            subtipo=subtipo,
        )
        second_record = Registro.objects.create(
            fecha='2026-03-02',
            item=self.item,
            periodo=self.period,
            descripcion='Registro visible sur',
            autor=self.second_employee,
            tipo=tipo,
            subtipo=subtipo,
        )
        beneficiary = Beneficiado.objects.create(
            nombre='Persona',
            apellido='Beneficiada',
            telefono=987654321,
        )
        gestion = GestionAtencion.objects.create(
            numero_gestion=1,
            fecha='2026-03-01',
        )
        first_attention = AtencionSocial.objects.create(
            fecha='2026-03-03T10:00:00Z',
            autor=self.employee,
            beneficiado=beneficiary,
            tipo=tipo,
            subtipo=subtipo,
            gestion_atencion=gestion,
            resultado='Atención norte',
        )
        second_attention = AtencionSocial.objects.create(
            fecha='2026-03-04T10:00:00Z',
            autor=self.second_employee,
            beneficiado=beneficiary,
            tipo=tipo,
            subtipo=subtipo,
            gestion_atencion=gestion,
            resultado='Atención sur',
        )
        first_agenda = Agenda.objects.create(
            delegacion=self.first_delegation,
            periodo=self.period,
        )
        second_agenda = Agenda.objects.create(
            delegacion=self.second_delegation,
            periodo=self.period,
        )
        first_commitment = Compromiso.objects.create(
            agenda=first_agenda,
            descripcion='Compromiso norte',
            fecha='2026-03-05T10:00:00Z',
            tipo=tipo,
            subtipo=subtipo,
        )
        second_commitment = Compromiso.objects.create(
            agenda=second_agenda,
            descripcion='Compromiso sur',
            fecha='2026-03-06T10:00:00Z',
            tipo=tipo,
            subtipo=subtipo,
        )
        self.client.force_login(self.admin)

        screens = (
            (
                'administracion:registros',
                'Registro visible norte',
                'Registro visible sur',
            ),
            (
                'administracion:atenciones-sociales',
                'Atención norte',
                'Atención sur',
            ),
            (
                'administracion:compromisos',
                'Compromiso norte',
                'Compromiso sur',
            ),
        )
        for route_name, included_text, excluded_text in screens:
            with self.subTest(route=route_name):
                response = self.client.get(
                    reverse(route_name),
                    {'delegacion': self.first_delegation.pk},
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, included_text)
                self.assertNotContains(response, excluded_text)
                exported = self.client.get(
                    reverse(route_name),
                    {'delegacion': self.first_delegation.pk, 'export': 'csv'},
                )
                self.assertEqual(exported.status_code, 200)
                self.assertIn(included_text, exported.content.decode('utf-8-sig'))

        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                entidad_afectada='Listado:registros',
            ).exists(),
        )
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                entidad_afectada='Listado:atenciones-sociales',
            ).exists(),
        )
        self.assertTrue(
            Historial.objects.filter(
                autor=self.admin,
                entidad_afectada='Listado:compromisos',
            ).exists(),
        )
        self.assertTrue(Registro.objects.filter(pk=first_record.pk).exists())
        self.assertTrue(Registro.objects.filter(pk=second_record.pk).exists())
        self.assertTrue(AtencionSocial.objects.filter(pk=first_attention.pk).exists())
        self.assertTrue(AtencionSocial.objects.filter(pk=second_attention.pk).exists())
        self.assertTrue(Compromiso.objects.filter(pk=first_commitment.pk).exists())
        self.assertTrue(Compromiso.objects.filter(pk=second_commitment.pk).exists())
