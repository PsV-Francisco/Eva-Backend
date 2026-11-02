from django.contrib.auth import get_user_model
from datetime import date
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from AdminApp.models import Cargo, Delegacion, Historial, ParametroSistema
from CoordinadorApp.models import (
    Desempeno,
    Funcion,
    Item,
    Periodo,
    PeriodoSemana,
    SolicitudAutorizacionPeriodo,
)
from django.db.models.deletion import ProtectedError
from CoordinadorApp.services import _semaforo, authorization_for, max_dias_autorizacion, porcentaje_esperado, record_authorization_use, resumen_cumplimiento, tendencias_cumplimiento, validate_authorization_expiry
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia
from config.permissions import PERMISSION_CATALOG, PERMISSION_DESCRIPTIONS
from AdminApp.templatetags.navigation_tags import sidebar_sections


class ClosedPeriodAuthorizationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coordinator = User.objects.create_user(email='coord-auth@test', password='password', cargo=Cargo.objects.create(nombre='coordinador'))
        self.admin = User.objects.create_user(email='admin-auth@test', password='password', cargo=Cargo.objects.create(nombre='admin'))
        self.employee = User.objects.create_user(email='employee-auth@test', password='password', cargo=Cargo.objects.create(nombre='funcionario'))
        self.period = Periodo.objects.create(nombre='Periodo cerrado auth', fecha_inicio='2026-01-01', fecha_fin='2026-01-31', estado=Periodo.Estado.CERRADO)

    def test_request_can_be_cancelled_and_admin_inbox_marks_old_pending(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(reverse('coordinador:solicitudes_autorizacion'), {
            'periodo': self.period.pk, 'funcionarios': [self.employee.pk], 'motivo': 'Corrección necesaria',
        })
        self.assertEqual(response.status_code, 302)
        request = SolicitudAutorizacionPeriodo.objects.get()
        request.creada_en = timezone.now() - timedelta(days=4)
        request.save(update_fields=['creada_en'])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('administracion:solicitudes-autorizacion'))
        self.assertContains(response, 'Pendiente por')
        self.client.force_login(self.coordinator)
        self.client.post(reverse('coordinador:solicitudes_autorizacion'), {'action': 'cancelar', 'solicitud_id': request.pk})
        request.refresh_from_db()
        self.assertEqual(request.estado, SolicitudAutorizacionPeriodo.Estado.CANCELADA)

    def test_expiry_limit_is_enforced_and_multiple_uses_keep_authorization_active(self):
        self.assertEqual(max_dias_autorizacion(), 7)
        self.assertNotEqual(validate_authorization_expiry(timezone.now() + timedelta(days=8)), '')
        request = SolicitudAutorizacionPeriodo.objects.create(
            periodo=self.period, solicitante=self.coordinator, alcances=['metas'], motivo='motivo',
            estado=SolicitudAutorizacionPeriodo.Estado.APROBADA,
            vence_en=timezone.now() + timedelta(days=1), aprobador=self.admin,
        )
        request.funcionarios.add(self.employee)
        self.assertIsNotNone(authorization_for(self.coordinator, self.period, funcionario=self.employee))
        record_authorization_use(request, self.coordinator)
        request.refresh_from_db()
        first_use = request.usada_en
        record_authorization_use(request, self.coordinator)
        request.refresh_from_db()
        self.assertEqual(request.usada_en, first_use)
        request.vence_en = timezone.now() - timedelta(seconds=1)
        request.save(update_fields=['vence_en'])
        self.assertIsNone(authorization_for(self.coordinator, self.period, funcionario=self.employee))
        request.refresh_from_db()
        self.assertEqual(request.estado, SolicitudAutorizacionPeriodo.Estado.VENCIDA)

    def test_valid_authorization_allows_multiple_closed_meta_mutations(self):
        function = Funcion.objects.create(nombre='Funcion auth')
        item_one = Item.objects.create(funcion=function, nombre='Item auth 1')
        item_two = Item.objects.create(funcion=function, nombre='Item auth 2')
        request = SolicitudAutorizacionPeriodo.objects.create(
            periodo=self.period, solicitante=self.coordinator, alcances=['metas'], motivo='motivo',
            estado=SolicitudAutorizacionPeriodo.Estado.APROBADA,
            vence_en=timezone.now() + timedelta(days=1), aprobador=self.admin,
        )
        request.funcionarios.add(self.employee)
        self.client.force_login(self.coordinator)
        for item in (item_one, item_two):
            response = self.client.post(reverse('coordinador:metas'), {
                'usuario': self.employee.pk, 'item': item.pk, 'periodo': self.period.pk,
                'meta': '10.00', 'ponderacion': '50.00',
            })
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Desempeno.objects.filter(periodo=self.period, usuario=self.employee).count(), 2)
        request.refresh_from_db()
        self.assertEqual(request.estado, SolicitudAutorizacionPeriodo.Estado.APROBADA)
        self.assertIsNotNone(request.usada_en)

    def test_revoked_authorization_is_not_usable_and_employee_scope_is_checked(self):
        request = SolicitudAutorizacionPeriodo.objects.create(
            periodo=self.period, solicitante=self.coordinator, alcances=['metas'], motivo='motivo',
            estado=SolicitudAutorizacionPeriodo.Estado.REVOCADA,
            vence_en=timezone.now() + timedelta(days=1), aprobador=self.admin,
        )
        request.funcionarios.add(self.employee)
        self.assertIsNone(authorization_for(self.coordinator, self.period, funcionario=self.employee))
        other = get_user_model().objects.create_user(email='other-auth@test', password='password')
        self.assertIsNone(authorization_for(self.coordinator, self.period, funcionario=other))


class TargetSchemaPeriodoSemanaTests(TestCase):
    def setUp(self):
        self.periodo = Periodo.objects.create(
            nombre='Período con semanas',
            fecha_inicio='2026-01-01',
            fecha_fin='2026-12-31',
        )

    def test_periodo_semana_creation_and_periodo_relation(self):
        semana = PeriodoSemana.objects.create(
            nombre='Primera semana',
            fecha_inicio='2026-01-05T00:00:00Z',
            fecha_fin='2026-01-11T23:59:59Z',
            estado='planificada',
            periodo=self.periodo,
        )

        semana.refresh_from_db()
        self.assertEqual(semana.periodo, self.periodo)
        self.assertEqual(self.periodo.semanas_objetivo.get(), semana)

    def test_periodo_semana_nullable_fields_accept_null(self):
        semana = PeriodoSemana.objects.create(
            nombre='Semana sin fechas',
            fecha_inicio=None,
            fecha_fin=None,
            estado=None,
            periodo=self.periodo,
        )

        semana.refresh_from_db()
        self.assertIsNone(semana.fecha_inicio)
        self.assertIsNone(semana.fecha_fin)
        self.assertIsNone(semana.estado)

    def test_periodo_with_semana_is_protected(self):
        PeriodoSemana.objects.create(
            nombre='Semana protegida',
            periodo=self.periodo,
        )

        with self.assertRaises(ProtectedError):
            self.periodo.delete()

    def test_periodo_semanas_have_distinct_primary_keys(self):
        first = PeriodoSemana.objects.create(nombre='Semana A', periodo=self.periodo)
        second = PeriodoSemana.objects.create(nombre='Semana B', periodo=self.periodo)

        self.assertNotEqual(first.pk, second.pk)


class ConsolidatedReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coordinator = User.objects.create_user(email='report-coord@test', password='password', cargo=Cargo.objects.create(nombre='coordinador'))
        self.cargo = Cargo.objects.create(nombre='analista')
        self.delegation = Delegacion.objects.create(nombre='DelegaciÃ³n Informe')
        self.period = Periodo.objects.create(nombre='PerÃ­odo informe abierto', fecha_inicio='2026-01-01', fecha_fin='2026-01-31')
        self.client.force_login(self.coordinator)

    def create_employee(self, index, **extra):
        values = {'email': f'report-{index}@test', 'password': 'password', 'cargo': self.cargo, 'delegacion': self.delegation}
        values.update(extra)
        return get_user_model().objects.create_user(**values)

    def test_default_period_and_filters_render_consolidated_summary(self):
        employee = self.create_employee(1)
        function = Funcion.objects.create(nombre='FunciÃ³n informe')
        item = Item.objects.create(funcion=function, nombre='Ãtem informe')
        Desempeno.objects.create(usuario=employee, item=item, periodo=self.period, meta=10, ponderacion=100)
        response = self.client.get(reverse('coordinador:informes'), {'delegacion': self.delegation.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.period.nombre)
        self.assertContains(response, 'Resumen consolidado')
        self.assertContains(response, 'DelegaciÃ³n Informe')
        self.assertContains(response, 'Bajo umbral')

    def test_html_table_is_paginated(self):
        for index in range(30):
            self.create_employee(index)
        response = self.client.get(reverse('coordinador:informes'))
        self.assertContains(response, '1 de 2')
        response = self.client.get(reverse('coordinador:informes'), {'page': 2})
        self.assertContains(response, '2 de 2')

    def test_csv_sanitizes_formula_cells_and_audits_export(self):
        self.create_employee(1, first_name='=1+1', last_name='Usuario')
        response = self.client.get(reverse('coordinador:informes'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        self.assertIn("'=1+1 Usuario", content)
        self.assertNotIn('\n=1+1 Usuario', content)
        self.assertTrue(Historial.objects.filter(accion='Exportar informe consolidado CSV', autor=self.coordinator).exists())

    def test_report_is_read_only_and_admin_can_access(self):
        self.assertEqual(self.client.post(reverse('coordinador:informes')).status_code, 405)
        admin = get_user_model().objects.create_user(email='report-admin@test', password='password', cargo=Cargo.objects.create(nombre='admin'))
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('coordinador:informes')).status_code, 200)


class HistoricalTrendsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coordinator = User.objects.create_user(
            email='trends-coord@test',
            password='password',
            cargo=Cargo.objects.create(nombre='coordinador'),
        )
        self.cargo_a = Cargo.objects.create(nombre='Analista tendencias')
        self.cargo_b = Cargo.objects.create(nombre='Técnico tendencias')
        self.delegation_a = Delegacion.objects.create(nombre='Delegación Norte')
        self.delegation_b = Delegacion.objects.create(nombre='Delegación Sur')
        self.alice = self.create_employee(
            'trends-alice@test', self.cargo_a, self.delegation_a,
        )
        self.bob = self.create_employee(
            'trends-bob@test', self.cargo_b, self.delegation_a,
        )
        self.charlie = self.create_employee(
            'trends-charlie@test', self.cargo_a, self.delegation_a,
        )
        self.diana = self.create_employee(
            'trends-diana@test', self.cargo_a, self.delegation_b,
        )
        self.periods = [
            Periodo.objects.create(
                nombre=f'Período tendencias {month}',
                fecha_inicio=date(2026, month, 1),
                fecha_fin=date(2026, month, 28),
            )
            for month in (1, 2, 3)
        ]
        self.function = Funcion.objects.create(nombre='Función tendencias')
        self.item = Item.objects.create(
            funcion=self.function,
            nombre='Ítem tendencias',
        )
        self.add_performance(self.alice, self.periods[0], 8)
        self.add_performance(self.bob, self.periods[0], 4)
        self.add_performance(self.alice, self.periods[1], 5)
        self.add_performance(self.diana, self.periods[1], 10)
        ParametroSistema.objects.update_or_create(
            clave=ParametroSistema.Clave.UMBRAL_DELEGACION,
            defaults={'valor': 60},
        )
        self.client.force_login(self.coordinator)

    def create_employee(self, email, cargo, delegation):
        return get_user_model().objects.create_user(
            email=email,
            password='password',
            cargo=cargo,
            delegacion=delegation,
        )

    def add_performance(self, user, period, activity_count):
        Desempeno.objects.create(
            usuario=user,
            item=self.item,
            periodo=period,
            meta=10,
            ponderacion=100,
        )
        for index in range(activity_count):
            record = Registro.objects.create(
                autor=user,
                item=self.item,
                periodo=period,
                fecha=period.fecha_inicio,
                descripcion=f'Actividad {user.email} {period.pk} {index}',
                estado=Registro.Estado.VALIDADA,
            )
            Evidencia.objects.create(
                registro=record,
                archivo=f'evidencias/tendencias-{record.pk}.pdf',
                estado=Evidencia.Estado.APROBADA,
            )

    def test_coordinator_and_administrator_access_but_other_cargo_is_denied(self):
        url = reverse('coordinador:tendencias')
        self.assertEqual(self.client.get(url).status_code, 200)

        administrator = get_user_model().objects.create_user(
            email='trends-admin@test',
            password='password',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        self.client.force_login(administrator)
        self.assertEqual(self.client.get(url).status_code, 200)

        employee = get_user_model().objects.create_user(
            email='trends-denied@test',
            password='password',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.client.force_login(employee)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_permission_catalog_allows_access_and_menu_visibility_by_permission(self):
        definition = next(
            permission for permission in PERMISSION_CATALOG
            if permission.codename == 'view_coordinator_trends'
        )
        self.assertEqual(definition.view_name, 'coordinador:tendencias')
        self.assertIn('evolución histórica', PERMISSION_DESCRIPTIONS[definition.codename])
        employee = get_user_model().objects.create_user(
            email='trends-permission@test',
            password='password',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        permission = Permission.objects.get(
            content_type__app_label='AdminApp',
            codename=definition.codename,
        )
        employee.user_permissions.add(permission)
        self.client.force_login(employee)
        self.assertEqual(self.client.get(reverse(definition.view_name)).status_code, 200)
        sections = sidebar_sections(
            (),
            (),
            ({'label': 'Tendencias históricas', 'url_name': definition.view_name},),
            definition.view_name,
            employee,
        )
        labels = [item['label'] for section in sections for item in section['items']]
        self.assertIn('Tendencias históricas', labels)

    def test_individual_and_combined_filters_limit_the_global_scope(self):
        url = reverse('coordinador:tendencias')
        cases = (
            ({'delegacion': self.delegation_a.pk}, 3),
            ({'cargo': self.cargo_a.pk}, 3),
            ({'funcionario': self.alice.pk}, 1),
            ({
                'delegacion': self.delegation_a.pk,
                'cargo': self.cargo_a.pk,
                'funcionario': self.alice.pk,
            }, 1),
        )
        for filters, expected_users in cases:
            with self.subTest(filters=filters):
                response = self.client.get(url, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context['series'][0]['funcionarios_sin_items']
                    + response.context['series'][0]['funcionarios_considerados'],
                    expected_users,
                )

    def test_series_averages_users_excludes_no_items_and_uses_configured_threshold(self):
        response = self.client.get(reverse('coordinador:tendencias'), {
            'delegacion': self.delegation_a.pk,
        })
        self.assertEqual(response.status_code, 200)
        first, second, third = response.context['series']
        self.assertEqual(first['funcionarios_considerados'], 2)
        self.assertEqual(first['funcionarios_sin_items'], 1)
        self.assertEqual(first['promedio_avance_real'], Decimal('60.00'))
        self.assertEqual(first['porcentaje_sobre_umbral'], Decimal('50.00'))
        self.assertEqual(second['funcionarios_considerados'], 1)
        self.assertEqual(second['funcionarios_sin_items'], 2)
        self.assertEqual(second['promedio_avance_real'], Decimal('50.00'))
        self.assertEqual(second['porcentaje_sobre_umbral'], Decimal('0.00'))
        self.assertEqual(third['funcionarios_considerados'], 0)
        self.assertEqual(response.context['threshold'], Decimal('60'))
        self.assertContains(response, 'Umbral 60,00%')

    def test_default_and_maximum_range_and_invalid_range_values(self):
        for index in range(13):
            Periodo.objects.create(
                nombre=f'Período rango {index}',
                fecha_inicio=date(2000 + index, 1, 1),
                fecha_fin=date(2000 + index, 1, 28),
            )
        url = reverse('coordinador:tendencias')
        response = self.client.get(url)
        self.assertEqual(response.context['period_limit'], 6)
        self.assertEqual(len(response.context['series']), 6)

        response = self.client.get(url, {'periodos': '9' * 100})
        self.assertEqual(response.context['period_limit'], 12)
        self.assertEqual(len(response.context['series']), 12)
        self.assertContains(response, 'rango máximo es 12')

        for invalid_value in ('texto', '0', '-2'):
            with self.subTest(invalid_value=invalid_value):
                response = self.client.get(url, {'periodos': invalid_value})
                self.assertEqual(response.context['period_limit'], 6)
                self.assertContains(response, 'rango indicado no es válido')

    def test_invalid_or_nonexistent_filter_ids_return_empty_results_with_message(self):
        url = reverse('coordinador:tendencias')
        cases = (
            {'delegacion': '999999'},
            {'cargo': '999999'},
            {'funcionario': '999999'},
            {'delegacion': 'texto'},
            {'cargo': '0'},
            {'funcionario': '-3'},
            {'delegacion': '9' * 100},
        )
        for filters in cases:
            with self.subTest(filters=filters):
                response = self.client.get(url, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['series'], [])
                self.assertContains(response, 'no hay resultados')

    def test_single_data_period_has_message_instead_of_empty_graph(self):
        response = self.client.get(
            reverse('coordinador:tendencias'),
            {'funcionario': self.bob.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['chart_points'], [])
        self.assertContains(response, 'al menos dos períodos')
        self.assertContains(response, '<table')

    def test_svg_and_equivalent_accessible_table_render_for_multiple_data_periods(self):
        response = self.client.get(
            reverse('coordinador:tendencias'),
            {'delegacion': self.delegation_a.pk},
        )
        self.assertContains(response, 'role="img"')
        self.assertContains(response, 'aria-label="Tendencias históricas')
        self.assertContains(response, '<title>Evolución del cumplimiento')
        self.assertContains(response, '<desc>')
        self.assertContains(response, 'Promedio de avance real')
        self.assertContains(response, 'Funcionarios sin ítems')
        self.assertContains(response, 'viewBox="0 0 760 340"')
        self.assertContains(response, 'class="trend-threshold"')

    def test_csv_has_utf8_bom_safe_accents_and_audits_export(self):
        unsafe_names = (
            '=Período histórico',
            '+Período histórico',
            '-Período histórico',
            '@Período histórico',
        )
        for index, name in enumerate(unsafe_names, 2027):
            Periodo.objects.create(
                nombre=name,
                fecha_inicio=date(index, 1, 1),
                fecha_fin=date(index, 1, 31),
            )
        response = self.client.get(
            reverse('coordinador:tendencias'),
            {'periodos': 12, 'export': 'csv'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        content = response.content.decode('utf-8-sig')
        for name in unsafe_names:
            self.assertIn(f"'{name}", content)
        self.assertIn('Funcionarios considerados', content)
        self.assertTrue(Historial.objects.filter(
            accion='Exportar tendencias históricas CSV',
            autor=self.coordinator,
            entidad_afectada='TendenciasHistoricas',
        ).exists())

    def test_endpoint_is_read_only_and_post_is_rejected(self):
        performances_before = Desempeno.objects.count()
        records_before = Registro.objects.count()
        response = self.client.post(reverse('coordinador:tendencias'), {
            'periodos': 12,
            'delegacion': self.delegation_a.pk,
        })
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Desempeno.objects.count(), performances_before)
        self.assertEqual(Registro.objects.count(), records_before)

    def test_service_uses_a_bounded_number_of_queries(self):
        users = [self.alice, self.bob, self.charlie, self.diana]
        with self.assertNumQueries(2):
            series = tendencias_cumplimiento(
                users,
                self.periods,
                cap=Decimal('150'),
                umbral=Decimal('60'),
            )
        self.assertEqual(len(series), len(self.periods))


class PeriodManagementTests(TestCase):
    def setUp(self):
        self.coordinator = get_user_model().objects.create_user(
            email='coordinador@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
        )
        self.client.force_login(self.coordinator)

    def create_period(self, **overrides):
        values = {
            'nombre': 'Período de prueba',
            'fecha_inicio': '2026-01-01',
            'fecha_fin': '2026-03-31',
        }
        values.update(overrides)
        return Periodo.objects.create(**values)

    def test_period_defaults_to_open(self):
        period = self.create_period()

        self.assertEqual(period.estado, Periodo.Estado.ABIERTO)

    def test_period_dates_cannot_overlap(self):
        self.create_period()

        response = self.client.post(reverse('coordinador:home'), {
            'nombre': 'Período superpuesto',
            'fecha_inicio': '2026-03-01',
            'fecha_fin': '2026-04-30',
            'estado': Periodo.Estado.ABIERTO,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Periodo.objects.filter(nombre='Período superpuesto').exists())
        self.assertContains(response, 'se superponen')

    def test_closed_period_cannot_be_edited_or_deleted(self):
        period = self.create_period(
            estado=Periodo.Estado.CERRADO,
            nombre='Período cerrado',
        )

        self.client.post(reverse('coordinador:home'), {
            'periodo_id': period.pk,
            'nombre': 'Cambio no permitido',
            'fecha_inicio': '2026-01-01',
            'fecha_fin': '2026-03-31',
            'estado': Periodo.Estado.ABIERTO,
        })
        self.client.post(reverse('coordinador:home'), {
            'action': 'eliminar',
            'periodo_id': period.pk,
        })

        period.refresh_from_db()
        self.assertEqual(period.nombre, 'Período cerrado')
        self.assertEqual(period.estado, Periodo.Estado.CERRADO)

    def test_period_with_measurements_is_closed_instead_of_deleted(self):
        period = self.create_period(nombre='Período con datos')
        function = Funcion.objects.create(nombre='Función de prueba')
        item = Item.objects.create(funcion=function, nombre='Ítem de prueba')
        Desempeno.objects.create(
            usuario=self.coordinator,
            item=item,
            periodo=period,
            meta=10,
            ponderacion=100,
        )

        response = self.client.post(reverse('coordinador:home'), {
            'action': 'eliminar',
            'periodo_id': period.pk,
        })

        period.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(period.estado, Periodo.Estado.ABIERTO)
        self.assertTrue(period.desempenos.exists())

        self.client.post(reverse('coordinador:home'), {
            'action': 'cerrar',
            'periodo_id': period.pk,
        })
        period.refresh_from_db()
        self.assertEqual(period.estado, Periodo.Estado.CERRADO)
        self.assertTrue(Historial.objects.filter(
            accion='Cerrar período',
            autor=self.coordinator,
            entidad_afectada=f'Periodo:{period.pk}',
        ).exists())

    def test_administrator_can_reopen_period_and_action_is_audited(self):
        administrator = get_user_model().objects.create_user(
            email='admin@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        period = self.create_period(
            estado=Periodo.Estado.CERRADO,
            nombre='Período para reabrir',
        )
        self.client.force_login(administrator)

        response = self.client.post(reverse('coordinador:home'), {
            'action': 'reabrir',
            'periodo_id': period.pk,
        })

        period.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(period.estado, Periodo.Estado.ABIERTO)
        audit = Historial.objects.get(
            accion='Reabrir período',
            entidad_afectada=f'Periodo:{period.pk}',
        )
        self.assertEqual(audit.autor, administrator)
        self.assertEqual(audit.valor_anterior['estado'], Periodo.Estado.CERRADO)
        self.assertEqual(audit.valor_nuevo['estado'], Periodo.Estado.ABIERTO)


class ComplianceCalculationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='funcionario-medicion@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.period = Periodo.objects.create(
            nombre='Semana laboral',
            fecha_inicio=date(2026, 10, 19),
            fecha_fin=date(2026, 10, 23),
        )
        self.function = Funcion.objects.create(nombre='Función medición')
        self.item = Item.objects.create(funcion=self.function, nombre='Atenciones')
        self.performance = Desempeno.objects.create(
            usuario=self.user,
            item=self.item,
            periodo=self.period,
            meta=10,
            ponderacion=50,
        )

    def add_approved_activity(self, index, *, duplicate_evidence=False):
        record = Registro.objects.create(
            autor=self.user,
            item=self.item,
            periodo=self.period,
            fecha='2026-10-20',
            descripcion=f'Actividad {index}',
        )
        record.estado = Registro.Estado.VALIDADA
        record.save(update_fields=['estado'])
        Evidencia.objects.create(
            registro=record,
            archivo=f'evidencias/{index}.pdf',
            estado=Evidencia.Estado.APROBADA,
        )
        if duplicate_evidence:
            Evidencia.objects.create(
                registro=record,
                archivo=f'evidencias/{index}-duplicada.pdf',
                estado=Evidencia.Estado.APROBADA,
            )

    def test_advance_counts_only_approved_activities_once(self):
        self.add_approved_activity(1, duplicate_evidence=True)
        pending = Registro.objects.create(
            autor=self.user,
            item=self.item,
            periodo=self.period,
            fecha='2026-10-20',
            descripcion='Actividad pendiente',
        )
        Evidencia.objects.create(
            registro=pending,
            archivo='evidencias/pendiente.pdf',
            estado=Evidencia.Estado.PENDIENTE,
        )

        summary = resumen_cumplimiento(
            [self.performance],
            hoy=date(2026, 10, 21),
        )

        self.assertEqual(summary['items'][0]['avance'], Decimal('1'))
        self.assertEqual(summary['items'][0]['cumplimiento'], Decimal('10.00'))

    def test_expected_progress_uses_weekdays_inclusive_of_period_dates(self):
        self.assertEqual(
            porcentaje_esperado(self.period, hoy=date(2026, 10, 21)),
            Decimal('60.00'),
        )


class CoordinatorDashboardTests(TestCase):
    def setUp(self):
        self.coordinator = get_user_model().objects.create_user(
            email='coordinador-tablero@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
        )
        self.client.force_login(self.coordinator)

    def test_coordinator_dashboard_shows_threshold_and_item_detail(self):
        period = Periodo.objects.create(
            nombre='Período tablero',
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 31),
        )
        function = Funcion.objects.create(nombre='Función tablero')
        item = Item.objects.create(funcion=function, nombre='Ítem tablero')
        Desempeno.objects.create(
            usuario=self.coordinator,
            item=item,
            periodo=period,
            meta=10,
            ponderacion=100,
        )

        response = self.client.get(reverse('coordinador:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Umbral fijo')
        self.assertContains(response, 'Ítem tablero')

    def test_coordinator_dashboard_without_items_shows_empty_message(self):
        response = self.client.get(reverse('coordinador:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sin ítems asignados')


class TrafficLightTests(SimpleTestCase):
    def test_green_amber_and_red_thresholds(self):
        expected = Decimal('60')
        self.assertEqual(_semaforo(Decimal('60'), expected), 'verde')
        self.assertEqual(_semaforo(Decimal('36'), expected), 'ambar')
        self.assertEqual(_semaforo(Decimal('35.99'), expected), 'rojo')


class CoordinatorManagementTests(TestCase):
    def setUp(self):
        self.coordinator = get_user_model().objects.create_user(
            email='coordinador-c1@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='coordinador'),
        )
        self.employee = get_user_model().objects.create_user(
            email='funcionario-c1@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.period = Periodo.objects.create(
            nombre='Período C1',
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 31),
        )
        self.function = Funcion.objects.create(nombre='Función C1')
        self.item = Item.objects.create(
            funcion=self.function, nombre='Ítem C1',
        )
        self.client.force_login(self.coordinator)

    def test_coordinator_scope_is_global_like_period_management(self):
        performance = Desempeno.objects.create(
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
            meta=10,
            ponderacion=100,
        )

        response = self.client.get(reverse('coordinador:metas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.employee.email)
        self.assertContains(
            self.client.get(
                reverse('coordinador:metas'),
                {'editar': performance.pk},
            ),
            self.employee.email,
        )

    def test_closed_period_meta_cannot_be_edited_or_deleted(self):
        self.period.estado = Periodo.Estado.CERRADO
        self.period.save(update_fields=['estado'])
        performance = Desempeno.objects.create(
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
            meta=10,
            ponderacion=100,
        )

        response = self.client.post(reverse('coordinador:metas'), {
            'action': 'guardar',
            'object_id': performance.pk,
            'usuario': self.employee.pk,
            'item': self.item.pk,
            'periodo': self.period.pk,
            'meta': '20',
            'ponderacion': '100',
        })
        self.assertEqual(response.status_code, 302)
        performance.refresh_from_db()
        self.assertEqual(performance.meta, 10)

        self.client.post(reverse('coordinador:metas'), {
            'action': 'eliminar', 'object_id': performance.pk,
        })
        self.assertTrue(Desempeno.objects.filter(pk=performance.pk).exists())

    def test_meta_with_activity_cannot_be_deleted(self):
        performance = Desempeno.objects.create(
            usuario=self.employee,
            item=self.item,
            periodo=self.period,
            meta=10,
            ponderacion=100,
        )
        Registro.objects.create(
            autor=self.employee,
            item=self.item,
            periodo=self.period,
            fecha='2026-10-02',
            descripcion='Actividad vinculada',
        )

        self.client.post(reverse('coordinador:metas'), {
            'action': 'eliminar', 'object_id': performance.pk,
        })

        self.assertTrue(Desempeno.objects.filter(pk=performance.pk).exists())

    def test_weight_listing_reports_exact_total(self):
        Desempeno.objects.create(
            usuario=self.employee, item=self.item, periodo=self.period,
            meta=10, ponderacion=100,
        )

        response = self.client.get(reverse('coordinador:ponderaciones'), {
            'periodo': self.period.pk,
            'funcionario': self.employee.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cumple 100 %')

    def test_saving_meta_warns_when_weight_total_is_not_100(self):
        response = self.client.post(
            reverse('coordinador:metas'),
            {
                'action': 'guardar',
                'usuario': self.employee.pk,
                'item': self.item.pk,
                'periodo': self.period.pk,
                'meta': '10',
                'ponderacion': '40',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'menor a 100%')

    def test_position_function_assignment_is_not_period_bound(self):
        response = self.client.post(reverse('coordinador:cargos_funciones'), {
            'action': 'guardar',
            'cargo': self.employee.cargo.pk,
            'funcion': self.function.pk,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.employee.cargo.asignaciones_funciones.filter(
                funcion=self.function,
            ).exists()
        )

    def test_non_coordinator_cannot_access_coordinator_management(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse('coordinador:ponderaciones'))

        self.assertEqual(response.status_code, 403)
