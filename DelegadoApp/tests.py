from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import Cargo, Delegacion
from CoordinadorApp.models import Desempeno, Funcion, Item, Periodo
from DelegadoApp.models import (
    Agenda,
    Ausencia,
    Compromiso,
    Felicitacion,
    Hito,
    Informe,
    Licencia,
    Reclamo,
    HistorialEstadoCompromiso,
)
from FuncionarioApp.models import Registro, Territorio, Subtipo, Tipo
from test_helpers import create_user


class DelegationWorkflowTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(nombre='Delegación central')
        self.other_delegation = Delegacion.objects.create(nombre='Delegación externa')
        self.delegate = create_user(
            email='delegado@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
            delegacion=self.delegation,
        )
        self.tipo = Tipo.objects.create(nombre='Tipo compromiso')
        self.subtipo = Subtipo.objects.create(
            nombre='Subtipo compromiso',
            tipo=self.tipo,
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
            tipo=self.tipo,
            subtipo=self.subtipo,
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
            tipo=self.tipo,
            subtipo=self.subtipo,
        )

        response = self.client.post(reverse('delegado:home'), {
            'action': 'estado',
            'compromiso_id': other_commitment.pk,
            'estado': Compromiso.Estado.REALIZADO,
        })

        self.assertEqual(response.status_code, 404)


class TargetSchemaDelegadoModelTests(TestCase):
    def setUp(self):
        self.delegacion = Delegacion.objects.create(nombre='Delegación para hitos')
        self.usuario = create_user(
            email='objetivo@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        self.periodo = Periodo.objects.create(
            nombre='Período objetivo',
            fecha_inicio='2026-01-01',
            fecha_fin='2026-12-31',
        )
        self.funcion = Funcion.objects.create(nombre='Función objetivo')
        self.item = Item.objects.create(funcion=self.funcion, nombre='Ítem objetivo')
        self.desempeno = Desempeno.objects.create(
            usuario=self.usuario,
            item=self.item,
            periodo=self.periodo,
            meta=10,
            ponderacion=100,
        )
        self.registro = Registro.objects.create(
            fecha='2026-05-01',
            item=self.item,
            periodo=self.periodo,
            descripcion='Registro objetivo',
            autor=self.usuario,
        )
        self.territorio = Territorio.objects.create(
            nombre='Territorio objetivo',
            delegacion=self.delegacion,
        )

    def test_felicitacion_creation_copies_performance_relations(self):
        felicitacion = Felicitacion.objects.create(
            evidencia='evidencia',
            fecha='2026-05-02',
            ubicacion='Ubicación',
            estado='aprobada',
            desempeno=self.desempeno,
        )

        felicitacion.refresh_from_db()
        self.assertEqual(felicitacion.usuario, self.usuario)
        self.assertEqual(felicitacion.item, self.item)
        self.assertEqual(felicitacion.periodo, self.periodo)

    def test_ausencia_creation_copies_performance_relations(self):
        ausencia = Ausencia.objects.create(
            fecha='2026-05-03T12:00:00Z',
            descripcion='Ausencia justificada',
            desempeno=self.desempeno,
        )

        ausencia.refresh_from_db()
        self.assertEqual(ausencia.usuario, self.usuario)
        self.assertEqual(ausencia.item, self.item)
        self.assertEqual(ausencia.periodo, self.periodo)

    def test_reclamo_creation_copies_performance_relations_and_allows_nulls(self):
        reclamo = Reclamo.objects.create(
            evidencia='x' * 200,
            fecha=None,
            ubicacion=None,
            estado=None,
            desempeno=self.desempeno,
        )

        reclamo.refresh_from_db()
        self.assertEqual(reclamo.usuario, self.usuario)
        self.assertEqual(reclamo.item, self.item)
        self.assertEqual(reclamo.periodo, self.periodo)
        self.assertIsNone(reclamo.fecha)
        self.assertIsNone(reclamo.ubicacion)
        self.assertIsNone(reclamo.estado)

    def test_licencia_creation_copies_performance_relations_and_allows_nulls(self):
        licencia = Licencia.objects.create(
            fecha_inicio='2026-05-04T00:00:00Z',
            fecha_fin='2026-05-05T00:00:00Z',
            tipo=None,
            descripcion=None,
            archivo='archivo',
            desempeno=self.desempeno,
        )

        licencia.refresh_from_db()
        self.assertEqual(licencia.usuario, self.usuario)
        self.assertEqual(licencia.item, self.item)
        self.assertIsNone(licencia.tipo)
        self.assertIsNone(licencia.descripcion)

    def test_hito_creation_copies_registration_relations_and_delegation(self):
        hito = Hito.objects.create(
            nombre='Hito de prueba',
            descripcion=None,
            fecha_termino='2026-06-01T12:00:00Z',
            recursos_asociados=2,
            estado='activo',
            evento_recurrente=False,
            incluir_agenda=True,
            periocidad='mensual',
            territorio=self.territorio,
            responsable=self.usuario,
            registro=self.registro,
        )

        hito.refresh_from_db()
        self.assertEqual(hito.delegacion, self.delegacion)
        self.assertEqual(hito.autor_registro, self.registro.autor)
        self.assertEqual(hito.item_registro, self.registro.item)
        self.assertEqual(hito.periodo_registro, self.registro.periodo)
        self.assertIsNone(hito.descripcion)

    def test_hito_clean_rejects_mismatched_registration_dimension(self):
        other_user = create_user(
            email='otro-objetivo@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        hito = Hito(
            nombre='Hito inconsistente',
            fecha_termino='2026-06-01T12:00:00Z',
            recursos_asociados=1,
            estado='activo',
            evento_recurrente=False,
            incluir_agenda=False,
            periocidad='anual',
            territorio=self.territorio,
            delegacion=self.delegacion,
            responsable=self.usuario,
            registro=self.registro,
            autor_registro=other_user,
            item_registro=self.item,
            periodo_registro=self.periodo,
        )

        with self.assertRaises(ValidationError) as raised:
            hito.clean()

        self.assertIn('autor_registro', raised.exception.error_dict)

    def test_felicitacion_clean_rejects_mismatched_performance_dimension(self):
        other_user = create_user(
            email='tercero-objetivo@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        felicitacion = Felicitacion(
            evidencia='evidencia',
            fecha='2026-05-02',
            ubicacion='Ubicación',
            estado='aprobada',
            desempeno=self.desempeno,
            usuario=other_user,
            item=self.item,
            periodo=self.periodo,
        )

        with self.assertRaises(ValidationError) as raised:
            felicitacion.clean()

        self.assertIn('usuario', raised.exception.error_dict)

    def test_all_performance_children_reject_incoherent_relations(self):
        other_user = create_user(
            email='cuarto-objetivo@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        cases = (
            (
                Ausencia,
                {
                    'fecha': '2026-05-03T12:00:00Z',
                    'descripcion': 'Ausencia',
                },
            ),
            (
                Reclamo,
                {
                    'evidencia': 'evidencia',
                    'fecha': None,
                    'ubicacion': None,
                    'estado': None,
                },
            ),
            (
                Licencia,
                {
                    'fecha_inicio': '2026-05-04T00:00:00Z',
                    'fecha_fin': '2026-05-05T00:00:00Z',
                    'archivo': 'archivo',
                },
            ),
        )

        for model, fields in cases:
            with self.subTest(model=model.__name__):
                child = model(
                    **fields,
                    desempeno=self.desempeno,
                    usuario=other_user,
                    item=self.item,
                    **({'periodo': self.periodo} if model is not Licencia else {}),
                )
                with self.assertRaises(ValidationError) as raised:
                    child.clean()
                self.assertIn('usuario', raised.exception.error_dict)

    def test_performance_relation_sync_is_persisted_with_update_fields(self):
        other_user = create_user(
            email='quinto-objetivo@sgr.test',
            password='Sgr-Test-Password-418!',
        )
        other_item = Item.objects.create(
            funcion=self.funcion,
            nombre='Otro ítem objetivo',
        )
        other_desempeno = Desempeno.objects.create(
            usuario=other_user,
            item=other_item,
            periodo=self.periodo,
            meta=5,
            ponderacion=50,
        )
        felicitacion = Felicitacion.objects.create(
            evidencia='evidencia',
            fecha='2026-05-02',
            ubicacion='Ubicación',
            estado='aprobada',
            desempeno=self.desempeno,
        )
        felicitacion.desempeno = other_desempeno
        felicitacion.save(update_fields=['desempeno'])
        felicitacion.refresh_from_db()

        self.assertEqual(felicitacion.usuario, other_user)
        self.assertEqual(felicitacion.item, other_item)

    def test_desempeno_with_felicitacion_is_protected(self):
        Felicitacion.objects.create(
            evidencia='evidencia',
            fecha='2026-05-02',
            ubicacion='Ubicación',
            estado='aprobada',
            desempeno=self.desempeno,
        )

        with self.assertRaises(ProtectedError):
            self.desempeno.delete()

    def test_registro_with_hito_is_protected(self):
        Hito.objects.create(
            nombre='Hito protegido',
            fecha_termino='2026-06-01T12:00:00Z',
            recursos_asociados=1,
            estado='activo',
            evento_recurrente=False,
            incluir_agenda=False,
            periocidad='anual',
            territorio=self.territorio,
            responsable=self.usuario,
            registro=self.registro,
        )

        with self.assertRaises(ProtectedError):
            self.registro.delete()

    def test_territorio_with_hito_is_protected(self):
        Hito.objects.create(
            nombre='Hito con territorio protegido',
            fecha_termino='2026-06-01T12:00:00Z',
            recursos_asociados=1,
            estado='activo',
            evento_recurrente=False,
            incluir_agenda=False,
            periocidad='anual',
            territorio=self.territorio,
            responsable=self.usuario,
            registro=self.registro,
        )

        with self.assertRaises(ProtectedError):
            self.territorio.delete()

    def test_informe_creation_and_nullable_ddl_fields(self):
        informe = Informe.objects.create(
            tipo='resumen',
            filtros='filtro=' + ('x' * 300),
            fecha_generacion='2026-05-06T12:00:00Z',
            formato='csv',
            autor=self.usuario,
        )

        informe.refresh_from_db()
        self.assertEqual(informe.autor, self.usuario)
        self.assertGreater(len(informe.filtros), 200)

    def test_performance_fk_uses_exact_accented_sql_column_name(self):
        self.assertEqual(
            Felicitacion._meta.get_field('desempeno').db_column,
            'DESEMPEÑO',
        )


class DelegationTrackingTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(nombre='Delegación central')
        self.other_delegation = Delegacion.objects.create(nombre='Delegación externa')
        self.delegate = create_user(
            email='delegado@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
            delegacion=self.delegation,
        )
        self.tipo = Tipo.objects.create(nombre='Tipo seguimiento')
        self.subtipo = Subtipo.objects.create(
            nombre='Subtipo seguimiento',
            tipo=self.tipo,
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
            tipo=self.tipo,
            subtipo=self.subtipo,
        )
        self.client.force_login(self.delegate)

    def test_summary_is_limited_to_delegate_own_delegation(self):
        employee_cargo = Cargo.objects.create(nombre='funcionario')
        own_employee = create_user(
            email='propio@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=employee_cargo,
            delegacion=self.delegation,
        )
        create_user(
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
        other_delegate = create_user(
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
