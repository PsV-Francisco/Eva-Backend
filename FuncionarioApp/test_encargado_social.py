from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from CoordinadorApp.services import resumen_cumplimiento
from FuncionarioApp.views import _es_encargado_social
from config.permissions import can_access_permission, has_cargo_access
from config.views import home_redirect


class EncargadoSocialComplianceTests(SimpleTestCase):
    def test_funcionario_cargo_and_encargado_social_role_access_dashboard(self):
        role = SimpleNamespace(nombre='Encargado Social', permisos='')
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            cargo=SimpleNamespace(nombre='Funcionario'),
            roles=[role],
            has_perm=lambda permission: False,
        )

        self.assertTrue(has_cargo_access(user, ('funcionario',)))
        self.assertTrue(can_access_permission(
            user,
            'access_employee_dashboard',
            ('funcionario',),
        ))

    def test_encargado_social_role_without_cargo_resolves_as_funcionario(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            cargo=None,
            roles=[SimpleNamespace(nombre='Encargado Social', permisos='')],
            has_perm=lambda permission: False,
        )

        self.assertTrue(can_access_permission(
            user,
            'access_employee_dashboard',
            ('funcionario',),
        ))

    def test_encargado_social_role_redirects_to_funcionario_dashboard(self):
        request = RequestFactory().get('/inicio/')
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            cargo=None,
            roles=[SimpleNamespace(nombre='Encargado Social')],
        )

        response = home_redirect(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('funcionario:home'))

    def test_unrelated_social_role_does_not_grant_funcionario_access(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            cargo=None,
            roles=[SimpleNamespace(nombre='Coordinador Social', permisos='')],
            has_perm=lambda permission: False,
        )

        self.assertFalse(has_cargo_access(user, ('funcionario',)))

    def test_es_encargado_social_helper(self):
        # Anonymous or None user
        self.assertFalse(_es_encargado_social(None))
        anon = SimpleNamespace(is_authenticated=False)
        self.assertFalse(_es_encargado_social(anon))

        # User with role Encargado Social via queryset mock
        class MockRoleQuerySet:
            def filter(self, **kwargs):
                return self
            def exists(self):
                return True

        user_with_role = SimpleNamespace(
            is_authenticated=True,
            roles=MockRoleQuerySet(),
            cargo=None,
        )
        self.assertTrue(_es_encargado_social(user_with_role))

        # User with cargo Encargado Social
        class MockEmptyRoleQuerySet:
            def filter(self, **kwargs):
                return self
            def exists(self):
                return False

        user_with_cargo = SimpleNamespace(
            is_authenticated=True,
            roles=MockEmptyRoleQuerySet(),
            cargo=SimpleNamespace(nombre='Encargado Social'),
        )
        self.assertTrue(_es_encargado_social(user_with_cargo))

        # Regular user without social role or cargo
        regular_user = SimpleNamespace(
            is_authenticated=True,
            roles=MockEmptyRoleQuerySet(),
            cargo=SimpleNamespace(nombre='Funcionario General'),
        )
        self.assertFalse(_es_encargado_social(regular_user))

    def test_resumen_cumplimiento_using_desempeno_avance(self):
        item1 = SimpleNamespace(nombre='Atención Individual', ponderacion=Decimal('60.0'))
        item2 = SimpleNamespace(nombre='Visitas Domiciliarias', ponderacion=Decimal('40.0'))
        periodo = SimpleNamespace(
            pk=1,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )

        desempeno1 = SimpleNamespace(
            usuario_id=10,
            item_id=1,
            periodo_id=1,
            item=item1,
            meta=Decimal('50.00'),
            avance=Decimal('25.00'),
            periodo=periodo,
        )
        desempeno2 = SimpleNamespace(
            usuario_id=10,
            item_id=2,
            periodo_id=1,
            item=item2,
            meta=Decimal('20.00'),
            avance=Decimal('10.00'),
            periodo=periodo,
        )

        performances = [desempeno1, desempeno2]
        counts = {
            (row.usuario_id, row.item_id, row.periodo_id): Decimal(row.avance)
            for row in performances
        }

        summary = resumen_cumplimiento(performances, counts=counts, cap=Decimal('100'))

        # Item 1: avance 25 / meta 50 = 50% cumplimiento; aporte 50% * 60% = 30%
        item1_res = summary['items'][0]
        self.assertEqual(item1_res['avance'], Decimal('25.00'))
        self.assertEqual(item1_res['ponderacion'], Decimal('60.0'))
        self.assertEqual(item1_res['cumplimiento'], Decimal('50.00'))
        self.assertEqual(item1_res['aporte'], Decimal('30.00'))

        # Item 2: avance 10 / meta 20 = 50% cumplimiento; aporte 50% * 40% = 20%
        item2_res = summary['items'][1]
        self.assertEqual(item2_res['avance'], Decimal('10.00'))
        self.assertEqual(item2_res['ponderacion'], Decimal('40.0'))
        self.assertEqual(item2_res['cumplimiento'], Decimal('50.00'))
        self.assertEqual(item2_res['aporte'], Decimal('20.00'))

        # Totales
        self.assertEqual(summary['total_avance'], Decimal('35.00'))
        self.assertEqual(summary['total_aporte'], Decimal('50.00'))

    def test_dashboard_template_renders_encargado_social_columns(self):
        desempeno = SimpleNamespace(
            item=SimpleNamespace(nombre='Atenciones Terreno'),
            meta=Decimal('20.00'),
            avance=Decimal('10.00'),
        )
        summary = {
            'items': [
                {
                    'desempeno': desempeno,
                    'ponderacion': Decimal('25.00'),
                    'avance': Decimal('10.00'),
                    'meta': Decimal('20.00'),
                    'cumplimiento': Decimal('50.00'),
                    'aporte': Decimal('12.50'),
                    'semaforo': 'verde',
                }
            ],
            'total_avance': Decimal('10.00'),
            'total_meta': Decimal('20.00'),
            'avance_real': Decimal('50.00'),
            'avance_esperado': Decimal('40.00'),
            'total_aporte': Decimal('12.50'),
            'ponderacion_completa': True,
        }
        context = {
            'sgr_role': 'Funcionario',
            'summary': summary,
            'item_count': 1,
            'es_encargado_social': True,
            'umbral_delegacion': Decimal('60.00'),
            'clasificacion_umbral': 'bajo',
            'periodos': [],
            'periodo_seleccionado': None,
        }

        html = render_to_string('FuncionarioApp/cumplimiento.html', context)

        # Check the 5 requested columns
        self.assertIn('<th>Item</th>', html)
        self.assertIn('<th>Ponderador</th>', html)
        self.assertIn('<th>Avance Actual</th>', html)
        self.assertIn('<th>% de cumplimiento</th>', html)
        self.assertIn('<th>Cumplimiento ponderado</th>', html)

        # Check values
        self.assertIn('Atenciones Terreno', html)
        self.assertTrue('25,00%' in html or '25.00%' in html)
        self.assertTrue('10,00' in html or '10.00' in html)
        self.assertTrue('50,00%' in html or '50.00%' in html)
        self.assertTrue('12,50%' in html or '12.50%' in html)

    def test_dashboard_template_renders_standard_columns_for_regular_employee(self):
        desempeno = SimpleNamespace(
            item=SimpleNamespace(nombre='Actividades Comunitarias'),
            meta=Decimal('10.00'),
            avance=Decimal('4.00'),
        )
        summary = {
            'items': [
                {
                    'desempeno': desempeno,
                    'ponderacion': Decimal('30.00'),
                    'avance': Decimal('4.00'),
                    'meta': Decimal('10.00'),
                    'cumplimiento': Decimal('40.00'),
                    'aporte': Decimal('12.00'),
                    'semaforo': 'ambar',
                }
            ],
            'total_avance': Decimal('4.00'),
            'total_meta': Decimal('10.00'),
            'avance_real': Decimal('40.00'),
            'avance_esperado': Decimal('50.00'),
            'total_aporte': Decimal('12.00'),
            'ponderacion_completa': True,
        }
        context = {
            'sgr_role': 'Funcionario',
            'summary': summary,
            'item_count': 1,
            'es_encargado_social': False,
            'umbral_delegacion': Decimal('60.00'),
            'clasificacion_umbral': 'bajo',
            'periodos': [],
            'periodo_seleccionado': None,
        }

        html = render_to_string('FuncionarioApp/cumplimiento.html', context)

        self.assertIn('<th>Ponderación</th>', html)
        self.assertIn('<th>Avance / Meta actual</th>', html)
        self.assertIn('<th>% cumplimiento</th>', html)
        self.assertNotIn('<th>Avance Actual</th>', html)
        self.assertNotIn('<th>Ponderador</th>', html)
