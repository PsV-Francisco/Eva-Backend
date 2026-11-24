from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from CoordinadorApp.views import _trend_chart


class HistoriasUsuarioDashboardTests(SimpleTestCase):
    def test_hu17_trend_chart_exposes_expected_and_real_points(self):
        series = [{
            'periodo': SimpleNamespace(nombre='Q1'),
            'funcionarios_considerados': 1,
            'promedio_avance_real': Decimal('35.00'),
            'promedio_esperado': Decimal('50.00'),
            'porcentaje_sobre_umbral': Decimal('20.00'),
        }, {
            'periodo': SimpleNamespace(nombre='Q2'),
            'funcionarios_considerados': 1,
            'promedio_avance_real': Decimal('60.00'),
            'promedio_esperado': Decimal('75.00'),
            'porcentaje_sobre_umbral': Decimal('40.00'),
        }]

        points, _, _, _ = _trend_chart(series, Decimal('60.00'))

        self.assertEqual(len(points), 2)
        self.assertIn('esperado_y', points[0])
        self.assertIn('promedio_y', points[0])

    def test_hu18_templates_expose_update_and_drill_down_contract(self):
        root = Path(__file__).resolve().parent.parent
        funcionario = (root / 'Templates/FuncionarioApp/cumplimiento.html').read_text(
            encoding='utf-8', errors='replace',
        )
        delegado = (root / 'Templates/DelegadoApp/resumen.html').read_text(
            encoding='utf-8', errors='replace',
        )

        self.assertIn('ultima_actualizacion', funcionario)
        self.assertIn('detail_records', funcionario)
        self.assertIn('ultima_actualizacion', delegado)
        self.assertIn('detail_records', delegado)

    def test_hu19_templates_expose_recent_activity_metrics(self):
        root = Path(__file__).resolve().parent.parent
        delegado = (root / 'Templates/DelegadoApp/resumen.html').read_text(
            encoding='utf-8', errors='replace',
        )
        supervisor = (root / 'Templates/SupervisorApp/index.html').read_text(
            encoding='utf-8', errors='replace',
        )

        for template in (delegado, supervisor):
            self.assertIn('dias_sin_ingreso', template)
            self.assertIn('promedio_diario', template)
