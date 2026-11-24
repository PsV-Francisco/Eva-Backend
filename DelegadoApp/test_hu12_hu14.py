from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import Cargo, Delegacion, Historial
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso
from DelegadoApp.services import marcar_compromisos_vencidos
from FuncionarioApp.models import JuntaVecino, Territorio, Tipo, Subtipo, Vecino
from test_helpers import create_user


class Fase1AgendaTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(nombre='Delegación Fase 1')
        self.period = Periodo.objects.create(
            nombre='Período Fase 1',
            fecha_inicio='2026-01-01',
            fecha_fin='2026-12-31',
        )
        self.agenda = Agenda.objects.create(delegacion=self.delegation, periodo=self.period)
        self.tipo = Tipo.objects.create(nombre='Tipo Fase 1')
        self.subtipo = Subtipo.objects.create(nombre='Subtipo Fase 1', tipo=self.tipo)
        self.delegate = create_user(
            email='fase1-delegado@example.com',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
            delegacion=self.delegation,
        )
        self.employee = create_user(
            email='fase1-funcionario@example.com',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
            delegacion=self.delegation,
        )
        territory = Territorio.objects.create(nombre='Territorio Fase 1', delegacion=self.delegation)
        junta = JuntaVecino.objects.create(
            nombre='Junta Fase 1', domicilio_legal='Dirección Fase 1', numero_rpj=1001,
            territorio=territory, delegacion=self.delegation,
        )
        self.neighbor = Vecino.objects.create(
            rut='12.345.678-5', nombre='José', apellido='Álvarez',
            territorio=territory, junta_vecino=junta, delegacion=self.delegation,
        )

    def make_commitment(self, **extra):
        values = {
            'agenda': self.agenda,
            'descripcion': 'Solicitud de iluminación pública',
            'fecha_compromiso': timezone.now() + timedelta(days=2),
            'tipo': self.tipo,
            'subtipo': self.subtipo,
            'solicitante': self.neighbor,
        }
        values.update(extra)
        return Compromiso.objects.create(**values)

    def test_search_normalizes_rut_without_accents_or_punctuation(self):
        self.make_commitment()
        self.client.force_login(self.employee)

        response = self.client.get(reverse('funcionario:agenda_busqueda_json'), {
            'periodo': self.period.pk,
            'q': '123456785',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        self.assertEqual(response.json()['results'][0]['applicant'], str(self.neighbor))

    def test_responsible_employee_can_update_state_and_observations(self):
        commitment = self.make_commitment()
        commitment.responsable.add(self.employee)
        self.client.force_login(self.employee)

        response = self.client.post(reverse('funcionario:agenda_colectiva'), {
            'action': 'estado_compromiso',
            'compromiso_id': commitment.pk,
            'periodo': self.period.pk,
            'estado': Compromiso.Estado.EN_PROCESO,
            'observaciones': 'Se coordinó visita en terreno.',
        })

        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.estado, Compromiso.Estado.EN_PROCESO)
        self.assertEqual(commitment.observaciones, 'Se coordinó visita en terreno.')
        self.assertTrue(HistorialEstadoCompromiso.objects.filter(compromiso=commitment).exists())
        self.assertTrue(Historial.objects.filter(entidad_afectada=f'Compromiso:{commitment.pk}').exists())

    def test_other_employee_is_read_only_on_post(self):
        commitment = self.make_commitment()
        self.client.force_login(self.employee)

        response = self.client.post(reverse('funcionario:agenda_colectiva'), {
            'action': 'estado_compromiso',
            'compromiso_id': commitment.pk,
            'estado': Compromiso.Estado.CERRADO,
        })

        self.assertEqual(response.status_code, 404)
        commitment.refresh_from_db()
        self.assertEqual(commitment.estado, Compromiso.Estado.INGRESADO)

    def test_expired_commitment_is_persisted_as_expired_and_audited(self):
        commitment = self.make_commitment(
            fecha_compromiso=timezone.now() - timedelta(minutes=1),
        )

        marcar_compromisos_vencidos(
            Compromiso.objects.filter(pk=commitment.pk),
            self.delegate,
        )

        commitment.refresh_from_db()
        self.assertEqual(commitment.estado, Compromiso.Estado.VENCIDO)
        history = HistorialEstadoCompromiso.objects.get(compromiso=commitment)
        self.assertEqual(history.estado_nuevo, Compromiso.Estado.VENCIDO)
        self.assertTrue(Historial.objects.filter(
            entidad_afectada=f'Compromiso:{commitment.pk}',
            accion='Vencer compromiso automáticamente',
        ).exists())
