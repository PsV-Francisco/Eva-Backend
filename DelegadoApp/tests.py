from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import Cargo, Delegacion
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso


class DelegationWorkflowTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(nombre='Delegación central')
        self.other_delegation = Delegacion.objects.create(nombre='Delegación externa')
        self.delegate = get_user_model().objects.create_user(
            email='delegado@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
            delegacion=self.delegation,
        )
        self.period = Periodo.objects.create(
            nombre='Período delegado',
            fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31',
        )
        self.agenda = Agenda.objects.create(
            delegacion=self.delegation,
            periodo=self.period,
        )
        self.commitment = Compromiso.objects.create(
            agenda=self.agenda,
            descripcion='Operativo comunitario',
            fecha='2026-10-25',
        )
        self.client.force_login(self.delegate)

    def test_state_change_records_previous_new_author_and_date(self):
        response = self.client.post(reverse('delegado:home'), {
            'action': 'estado',
            'compromiso_id': self.commitment.pk,
            'estado': Compromiso.Estado.EN_PROCESO,
        })

        self.assertEqual(response.status_code, 302)
        self.commitment.refresh_from_db()
        history = HistorialEstadoCompromiso.objects.get(compromiso=self.commitment)
        self.assertEqual(self.commitment.estado, Compromiso.Estado.EN_PROCESO)
        self.assertEqual(history.estado_anterior, Compromiso.Estado.INGRESADO)
        self.assertEqual(history.estado_nuevo, Compromiso.Estado.EN_PROCESO)
        self.assertEqual(history.autor, self.delegate)
        self.assertIsNotNone(history.fecha)

    def test_closed_period_commitment_is_read_only(self):
        self.period.estado = Periodo.Estado.CERRADO
        self.period.save(update_fields=['estado'])

        response = self.client.post(reverse('delegado:home'), {
            'action': 'estado',
            'compromiso_id': self.commitment.pk,
            'estado': Compromiso.Estado.REALIZADO,
        })

        self.assertEqual(response.status_code, 302)
        self.commitment.refresh_from_db()
        self.assertEqual(self.commitment.estado, Compromiso.Estado.INGRESADO)
        self.assertFalse(HistorialEstadoCompromiso.objects.exists())

    def test_delegate_cannot_change_commitment_in_another_delegation(self):
        other_agenda = Agenda.objects.create(
            delegacion=self.other_delegation,
            periodo=self.period,
        )
        other_commitment = Compromiso.objects.create(
            agenda=other_agenda,
            descripcion='Privado de otra delegación',
            fecha='2026-10-25',
        )

        response = self.client.post(reverse('delegado:home'), {
            'action': 'estado',
            'compromiso_id': other_commitment.pk,
            'estado': Compromiso.Estado.REALIZADO,
        })

        self.assertEqual(response.status_code, 404)

    def test_summary_is_limited_to_delegate_own_delegation(self):
        employee_cargo = Cargo.objects.create(nombre='funcionario')
        own_employee = get_user_model().objects.create_user(
            email='propio@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
            delegacion=self.delegation,
        )
        get_user_model().objects.create_user(
            email='ajeno@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
            delegacion=self.other_delegation,
        )

        response = self.client.get(
            reverse('delegado:resumen'),
            {'periodo': self.period.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['usuario'] for row in response.context['funcionarios']],
            [own_employee],
        )

    def test_public_tracking_page_access_without_login_and_hides_sensitive_data(self):
        self.commitment.seguimiento_token = 'token-publico-123'
        self.commitment.seguimiento_activo = True
        self.commitment.seguimiento_expira = None
        self.commitment.descripcion = 'Compromiso público de ejemplo'
        self.commitment.solicitante = 'Ana Solicitante'
        self.commitment.observaciones = 'Observación interna no visible'
        self.commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo', 'seguimiento_expira', 'descripcion', 'solicitante', 'observaciones'])

        response = self.client.get(reverse('seguimiento_publico', args=['token-publico-123']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Código de gestión')
        self.assertContains(response, 'Compromiso público de ejemplo')
        self.assertNotContains(response, 'Ana Solicitante')
        self.assertNotContains(response, 'Observación interna no visible')
        self.assertContains(response, 'noindex')

    def test_public_tracking_rejects_invalid_regenerated_deactivated_and_expired_tokens(self):
        self.commitment.seguimiento_token = 'token-activo'
        self.commitment.seguimiento_activo = True
        self.commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo'])

        response = self.client.get(reverse('seguimiento_publico', args=['token-activo']))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('seguimiento_publico', args=['token-invalido']))
        self.assertEqual(response.status_code, 404)

        self.commitment.seguimiento_token = 'token-nuevo'
        self.commitment.seguimiento_activo = True
        self.commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo'])
        response = self.client.get(reverse('seguimiento_publico', args=['token-activo']))
        self.assertEqual(response.status_code, 404)

        self.commitment.seguimiento_token = 'token-desactivado'
        self.commitment.seguimiento_activo = False
        self.commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo'])
        response = self.client.get(reverse('seguimiento_publico', args=['token-desactivado']))
        self.assertEqual(response.status_code, 404)

        self.commitment.seguimiento_token = 'token-vencido'
        self.commitment.seguimiento_activo = True
        self.commitment.seguimiento_expira = timezone.now() - timedelta(minutes=5)
        self.commitment.save(update_fields=['seguimiento_token', 'seguimiento_activo', 'seguimiento_expira'])
        response = self.client.get(reverse('seguimiento_publico', args=['token-vencido']))
        self.assertEqual(response.status_code, 410)

    def test_unauthorized_user_cannot_manage_public_tracking_link(self):
        other_delegate = get_user_model().objects.create_user(
            email='delegado-otro@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.get_or_create(nombre='delegado')[0],
            delegacion=self.other_delegation,
        )
        other_client = self.client_class()
        other_client.force_login(other_delegate)
        response = other_client.post(reverse('delegado:home'), {
            'action': 'seguimiento_regenerar',
            'compromiso_id': self.commitment.pk,
        })
        self.assertEqual(response.status_code, 404)
