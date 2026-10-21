from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import Cargo, Delegacion, SubAtencion, TipoAtencion
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso
from FuncionarioApp.models import (
    AtencionSocial,
    CasoSocial,
    GestionAtencion,
    Solicitante,
)


class SocialCaseTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(
            nombre='Delegación de atención',
        )
        self.attention_type = TipoAtencion.objects.create(
            codigo='TAT-SOC',
            nombre='Apoyo familiar',
        )
        self.subattention = SubAtencion.objects.create(
            codigo='SAT-SOC',
            nombre='Orientación social',
            tipo_atencion=self.attention_type,
        )
        self.user = get_user_model().objects.create_user(
            email='funcionario-social@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
            delegacion=self.delegation,
        )
        self.client.force_login(self.user)

    def create_case(self):
        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'identificador': '12.345.678-k',
            'nombre_solicitante': 'Persona solicitante',
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': self.subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': 'Evaluación inicial',
            'observaciones': '',
        })
        self.assertEqual(response.status_code, 302)
        return CasoSocial.objects.latest('pk')

    def post_attention(self, case, index):
        return self.client.post(
            reverse('funcionario:atencion_social'),
            {
                'action': 'agregar_atencion',
                'caso_id': case.pk,
                'fecha': f'2026-10-{20 + index:02d}',
                'observaciones': f'Seguimiento {index}',
                'evidencia': SimpleUploadedFile(
                    f'atencion-{index}.pdf',
                    b'%PDF-1.4\ncontenido de prueba',
                    content_type='application/pdf',
                ),
            },
        )

    def test_case_accepts_three_evidenced_attentions_and_blocks_a_fourth(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            case = self.create_case()
            for index in range(1, 4):
                response = self.post_attention(case, index)
                self.assertEqual(response.status_code, 302)

            response = self.post_attention(case, 4)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(GestionAtencion.objects.filter(
                atencion=case.atencion_social,
            ).count(), 3)
            self.assertEqual(
                case.atencion_social.gestiones.filter(evidencias__isnull=False).distinct().count(),
                3,
            )
            self.assertContains(response, 'máximo de 3 atenciones')

    def test_case_intake_records_context_and_generated_code(self):
        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'identificador': '12.345.678-k',
            'nombre_solicitante': 'Persona solicitante',
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': self.subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': 'Evaluación inicial',
            'observaciones': '',
            'delegacion': '999999',
            'usuario': '999999',
            'fecha': '2000-01-01',
        })

        self.assertRedirects(response, reverse('funcionario:atencion_social'))
        case = CasoSocial.objects.get()
        attention = case.atencion_social
        self.assertContains(self.client.get(reverse('funcionario:atencion_social')), str(case.codigo))
        self.assertEqual(attention.usuario, self.user)
        self.assertEqual(attention.delegacion, self.delegation)
        self.assertEqual(attention.fecha, timezone.localdate())
        self.assertEqual(attention.tipo_atencion_catalogo, self.attention_type)
        self.assertEqual(attention.sub_atencion, self.subattention)
        self.assertEqual(attention.solicitante.identificador, '12.345.678-K')
        self.assertEqual(attention.descripcion, 'Solicitud de orientación familiar')

    def test_case_intake_rejects_subattention_of_another_type(self):
        other_type = TipoAtencion.objects.create(
            codigo='TAT-OTR',
            nombre='Otro tipo',
        )
        other_subattention = SubAtencion.objects.create(
            codigo='SAT-OTR',
            nombre='Otra sub atención',
            tipo_atencion=other_type,
        )

        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'identificador': '12.345.678-k',
            'nombre_solicitante': 'Persona solicitante',
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': other_subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': '',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AtencionSocial.objects.exists())

    def test_solicitante_lookup_is_limited_to_active_delegation(self):
        applicant = Solicitante.objects.create(
            identificador='12345678-K',
            nombre='Persona solicitante',
            delegacion=self.delegation,
        )
        other_delegation = Delegacion.objects.create(
            nombre='Otra delegación de atención',
        )
        Solicitante.objects.create(
            identificador='87654321-0',
            nombre='Otra persona',
            delegacion=other_delegation,
        )

        for query in ('Persona', '12345678'):
            with self.subTest(query=query):
                response = self.client.get(
                    reverse('funcionario:buscar_solicitantes'),
                    {'q': query},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [result['pk'] for result in response.json()['results']],
                    [applicant.pk],
                )

    def test_subattention_endpoint_returns_only_active_children(self):
        self.subattention.estado = SubAtencion.Estado.INACTIVO
        self.subattention.save(update_fields=['estado'])
        active_subattention = SubAtencion.objects.create(
            codigo='SAT-SOC-ACT',
            nombre='Orientación activa',
            tipo_atencion=self.attention_type,
        )
        inactive_type = TipoAtencion.objects.create(
            codigo='TAT-INAC',
            nombre='Tipo inactivo',
            estado=TipoAtencion.Estado.INACTIVO,
        )
        SubAtencion.objects.create(
            codigo='SAT-INAC',
            nombre='Sub atención inactiva',
            tipo_atencion=inactive_type,
        )

        response = self.client.get(
            reverse(
                'funcionario:subatenciones_tipo',
                args=[self.attention_type.pk],
            ),
        )
        inactive_response = self.client.get(
            reverse('funcionario:subatenciones_tipo', args=[inactive_type.pk]),
        )

        self.assertEqual(
            [item['pk'] for item in response.json()['results']],
            [active_subattention.pk],
        )
        self.assertEqual(inactive_response.json()['results'], [])

    def test_solicitante_id_from_another_delegation_is_rejected(self):
        other_delegation = Delegacion.objects.create(
            nombre='Delegación privada',
        )
        foreign_applicant = Solicitante.objects.create(
            identificador='99999999-K',
            nombre='Persona de otra delegación',
            delegacion=other_delegation,
        )

        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'solicitante_registrado': foreign_applicant.pk,
            'identificador': foreign_applicant.identificador,
            'nombre_solicitante': foreign_applicant.nombre,
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': self.subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': '',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertEqual(Solicitante.objects.count(), 1)

    def test_switching_delegation_scopes_cases_and_solicitantes(self):
        self.create_case()
        second_delegation = Delegacion.objects.create(
            nombre='Delegación secundaria de atención',
        )
        self.user.delegaciones_autorizadas.add(second_delegation)
        session = self.client.session
        session['active_delegation_id'] = second_delegation.pk
        session.save()

        response = self.client.get(reverse('funcionario:atencion_social'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['case_count'], 0)

        second_case = self.create_case()
        self.assertEqual(second_case.atencion_social.delegacion, second_delegation)
        self.assertEqual(
            second_case.atencion_social.solicitante.delegacion,
            second_delegation,
        )

    def test_user_without_active_delegation_cannot_create_case(self):
        user = get_user_model().objects.create_user(
            email='funcionario-sin-delegacion@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=self.user.cargo,
        )
        self.client.force_login(user)

        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'identificador': '12.345.678-k',
            'nombre_solicitante': 'Persona solicitante',
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': self.subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': '',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No tienes una delegación activa autorizada')
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertFalse(Solicitante.objects.exists())

    def test_cancel_does_not_create_case_or_applicant(self):
        response = self.client.get(reverse('funcionario:atencion_social'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertFalse(Solicitante.objects.exists())

    def test_user_cannot_add_attention_to_another_users_case(self):
        case_record = AtencionSocial.objects.create(
            usuario=self.user,
            tipo_atencion='Caso privado',
            fecha='2026-10-20',
        )
        case = CasoSocial.objects.create(atencion_social=case_record)
        other_user = get_user_model().objects.create_user(
            email='otro-funcionario@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=self.user.cargo,
        )
        self.client.force_login(other_user)

        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'agregar_atencion',
            'caso_id': case.pk,
            'fecha': '2026-10-21',
            'observaciones': 'No autorizado',
        })

        self.assertEqual(response.status_code, 404)
        self.assertFalse(GestionAtencion.objects.filter(atencion=case_record).exists())

    def test_employee_pages_require_employee_cargo(self):
        user = get_user_model().objects.create_user(
            email='delegado-social@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
        )
        self.client.force_login(user)

        for route in (
            'funcionario:atencion_social',
            'funcionario:agenda_colectiva',
            'funcionario:cumplimiento',
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)

    def test_assigned_employee_can_update_commitment_with_history(self):
        delegation = Delegacion.objects.create(nombre='Delegación de agenda')
        self.user.delegacion = delegation
        self.user.save(update_fields=['delegacion'])
        period = Periodo.objects.create(
            nombre='Agenda de funcionario',
            fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31',
        )
        agenda = Agenda.objects.create(delegacion=delegation, periodo=period)
        commitment = Compromiso.objects.create(
            agenda=agenda,
            descripcion='Compromiso asignado',
            fecha='2026-10-25',
        )
        commitment.responsables.add(self.user)

        response = self.client.post(reverse('funcionario:agenda_colectiva'), {
            'action': 'estado_compromiso',
            'compromiso_id': commitment.pk,
            'estado': Compromiso.Estado.REALIZADO,
            'periodo': period.pk,
        })

        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        history = HistorialEstadoCompromiso.objects.get(compromiso=commitment)
        self.assertEqual(commitment.estado, Compromiso.Estado.REALIZADO)
        self.assertEqual(history.estado_anterior, Compromiso.Estado.INGRESADO)
        self.assertEqual(history.estado_nuevo, Compromiso.Estado.REALIZADO)
        self.assertEqual(history.autor, self.user)

    def test_unassigned_employee_cannot_update_commitment(self):
        delegation = Delegacion.objects.create(nombre='Delegación restringida')
        self.user.delegacion = delegation
        self.user.save(update_fields=['delegacion'])
        period = Periodo.objects.create(
            nombre='Agenda restringida',
            fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31',
        )
        agenda = Agenda.objects.create(delegacion=delegation, periodo=period)
        commitment = Compromiso.objects.create(
            agenda=agenda,
            descripcion='No asignado',
            fecha='2026-10-25',
        )

        response = self.client.post(reverse('funcionario:agenda_colectiva'), {
            'action': 'estado_compromiso',
            'compromiso_id': commitment.pk,
            'estado': Compromiso.Estado.REALIZADO,
            'periodo': period.pk,
        })

        self.assertEqual(response.status_code, 404)
        commitment.refresh_from_db()
        self.assertEqual(commitment.estado, Compromiso.Estado.INGRESADO)
