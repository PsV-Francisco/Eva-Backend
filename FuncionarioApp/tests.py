from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from AdminApp.models import Cargo, Delegacion
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso
from FuncionarioApp.models import AtencionSocial, CasoSocial, GestionAtencion


class SocialCaseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='funcionario-social@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
        )
        self.client.force_login(self.user)

    def create_case(self):
        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'tipo_atencion': 'Apoyo familiar',
            'fecha': '2026-10-20',
            'resultado': 'Evaluación inicial',
            'observaciones': '',
        })
        self.assertEqual(response.status_code, 302)
        return CasoSocial.objects.get()

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
