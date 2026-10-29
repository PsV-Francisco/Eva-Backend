from django.contrib.auth import get_user_model
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from AdminApp.models import Cargo, Historial
from CoordinadorApp.models import Desempeno, Funcion, Item, Periodo
from CoordinadorApp.services import _semaforo, porcentaje_esperado, resumen_cumplimiento
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


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


class TrafficLightTests(SimpleTestCase):
    def test_green_amber_and_red_thresholds(self):
        expected = Decimal('60')
        self.assertEqual(_semaforo(Decimal('60'), expected), 'verde')
        self.assertEqual(_semaforo(Decimal('36'), expected), 'ambar')
        self.assertEqual(_semaforo(Decimal('35.99'), expected), 'rojo')
