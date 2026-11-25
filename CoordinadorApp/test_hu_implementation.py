from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase

from AdminApp.models import Delegacion, Usuario
from CoordinadorApp.models import Desempeno, Item, Periodo
from CoordinadorApp.services import porcentaje_esperado, resumen_cumplimiento
from DelegadoApp.models import Agenda, Ausencia, Compromiso, HistorialReasignacionCompromiso
from DelegadoApp.services import actualizar_compromiso
from FuncionarioApp.models import Registro, Subtipo, Tipo
from SupervisorApp.models import ObservacionRegistro


class HU07ComplianceTests(SimpleTestCase):
    def test_real_activity_count_is_kept_while_item_is_capped_at_120(self):
        periodo = type('PeriodoStub', (), {'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 1, 31)})()
        desempeno = type('DesempenoStub', (), {
            'usuario_id': 1, 'item_id': 2, 'periodo_id': 3,
            'meta': Decimal('1'), 'ponderacion': Decimal('50'),
            'periodo': periodo, 'usuario': None,
        })()
        summary = resumen_cumplimiento(
            [desempeno], counts={(1, 2, 3): Decimal('3')}, cap=Decimal('120'),
        )
        self.assertEqual(summary['items'][0]['avance'], Decimal('3'))
        self.assertEqual(summary['items'][0]['cumplimiento'], Decimal('120.00'))
        self.assertEqual(summary['items'][0]['aporte'], Decimal('60.00'))


class HU15HU24HU37Tests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(email='delegado@example.com', password='x')
        self.other = Usuario.objects.create_user(email='funcionario@example.com', password='x')
        self.delegation = Delegacion.objects.create(nombre='Delegación de prueba')
        self.period = Periodo.objects.create(nombre='Período de prueba', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31))
        self.item = Item.objects.create(nombre='Ítem de prueba')
        self.tipo = Tipo.objects.create(nombre='Tipo de prueba')
        self.subtipo = Subtipo.objects.create(nombre='Subtipo de prueba', tipo=self.tipo)
        self.desempeno = Desempeno.objects.create(usuario=self.other, item=self.item, periodo=self.period, meta=10, ponderacion=50)
        self.agenda = Agenda.objects.create(delegacion=self.delegation, periodo=self.period)
        self.compromiso = Compromiso.objects.create(
            agenda=self.agenda, descripcion='Compromiso de prueba', tipo=self.tipo,
            subtipo=self.subtipo, fecha_solicitud='2026-01-05T09:00:00Z',
            fecha_compromiso='2026-01-06T09:00:00Z',
        )
        self.compromiso.responsable.add(self.user)

    def test_hu15_requires_reason_and_persists_reassignment_history(self):
        with self.assertRaises(ValidationError):
            actualizar_compromiso(compromiso=self.compromiso, autor=self.user, responsables=[self.other])
        actualizar_compromiso(
            compromiso=self.compromiso, autor=self.user, responsables=[self.other],
            motivo='Redistribución de carga',
        )
        history = HistorialReasignacionCompromiso.objects.get(compromiso=self.compromiso)
        self.assertEqual(history.responsables_anteriores, [self.user.pk])
        self.assertEqual(history.responsables_nuevos, [self.other.pk])
        self.assertEqual(history.motivo, 'Redistribución de carga')

    def test_hu24_observation_thread_is_chronological(self):
        registro = Registro.objects.create(
            fecha=date(2026, 1, 5), item=self.item, periodo=self.period,
            descripcion='Actividad', autor=self.other, tipo=self.tipo, subtipo=self.subtipo,
        )
        first = ObservacionRegistro.objects.create(registro=registro, autor=self.other, comentario='Primera observación')
        second = ObservacionRegistro.objects.create(registro=registro, autor=self.user, comentario='Segundo comentario')
        self.assertEqual(list(registro.observaciones_cronologicas.values_list('pk', flat=True)), [first.pk, second.pk])

    def test_hu37_absence_range_is_used_without_double_counting(self):
        Ausencia.objects.create(
            fecha='2026-01-05T00:00:00Z', fecha_inicio=date(2026, 1, 5), fecha_fin=date(2026, 1, 6),
            tipo=Ausencia.Tipo.VACACIONES, descripcion='Vacaciones', desempeno=self.desempeno,
            usuario=self.other, item=self.item, periodo=self.period,
        )
        self.assertEqual(porcentaje_esperado(self.period, date(2026, 1, 31), self.other), Decimal('100.00'))
