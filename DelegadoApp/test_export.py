from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from openpyxl import load_workbook

from DelegadoApp.views import _resumen_excel_response


class DelegadoExcelExportTests(SimpleTestCase):
    @patch('DelegadoApp.views.registrar_historial')
    def test_summary_export_is_a_formatted_xlsx_with_hu19_columns(self, _audit):
        user = SimpleNamespace(
            email='funcionario@example.com',
            get_full_name=lambda: 'Funcionaria Ejemplo',
        )
        request = SimpleNamespace(user=user)
        row = {
            'usuario': user,
            'cumplimiento': 75,
            'esperado': 80,
            'semaforo': 'verde',
            'ultimo_registro': 'Atención vecinal',
            'fecha_ultimo_registro': date(2026, 11, 20),
            'dias_sin_ingreso': 4,
            'promedio_diario': 1.25,
        }

        response = _resumen_excel_response(
            request=request,
            delegation='Delegación Centro',
            period=SimpleNamespace(pk=7, nombre='Trimestre 4'),
            rows=[row],
        )

        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook['Resumen']
        headers = [cell.value for cell in sheet[7]]
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('.xlsx', response['Content-Disposition'])
        self.assertEqual(headers, [
            'Funcionario', 'Correo', 'Cumplimiento (%)', 'Esperado (%)',
            'Semáforo', 'Último registro', 'Fecha último registro',
            'Días sin ingreso', 'Promedio diario',
        ])
        self.assertEqual(sheet['A1'].value, 'Resumen de desempeño de delegación')
        self.assertEqual(sheet['E8'].fill.fgColor.rgb[-6:], 'DCFCE7')
        self.assertEqual(sheet['C8'].number_format, '0.00"%"')
        self.assertGreaterEqual(sheet.column_dimensions['B'].width, 30)
