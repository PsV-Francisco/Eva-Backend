from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from AdminApp.models import (
    Cargo,
    Delegacion,
    Historial,
    ParametroSistema,
    UsuarioCargo,
    UsuarioDelegacion,
)
from CoordinadorApp.models import Desempeno, Item, Periodo
from CoordinadorApp.models import AtencionSocial, GestionAtencion
from django.test import Client
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso
from FuncionarioApp.models import (
    Beneficiado,
    CargoJv,
    JuntaVecino as JuntaVecinos,
    Subtipo as SubAtencion,
    Territorio,
    Tipo,
    Vecino,
)
from SupervisorApp.models import Evidencia
from test_helpers import create_user


class SocialCaseTests(TestCase):
    def setUp(self):
        self.delegation = Delegacion.objects.create(
            nombre='Delegación de atención',
        )
        self.territory = Territorio.objects.create(
            nombre='Norte',
            delegacion=self.delegation,
        )
        self.attention_type = Tipo.objects.create(
            nombre='Apoyo familiar',
        )
        self.subattention = SubAtencion.objects.create(
            nombre='Orientación social',
            tipo=self.attention_type,
        )
        self.user = create_user(
            email='funcionario-social@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='funcionario'),
            delegacion=self.delegation,
        )
        self.client.force_login(self.user)

    def test_home_is_personal_dashboard_and_activities_have_own_route(self):
        response = self.client.get(reverse('funcionario:home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'FuncionarioApp/cumplimiento.html')
        self.assertContains(response, 'Tablero Personal')
        self.assertNotContains(response, 'NUEVA ACTIVIDAD')
        self.assertEqual(
            self.client.get(reverse('funcionario:gestion_actividades')).status_code,
            200,
        )

    def test_old_compliance_url_redirects_to_personal_dashboard(self):
        response = self.client.get(reverse('funcionario:cumplimiento'))

        self.assertRedirects(response, reverse('funcionario:home'))

    def test_personal_and_delegate_views_classify_same_employee_with_same_threshold(self):
        ParametroSistema.objects.update_or_create(
            clave=ParametroSistema.Clave.UMBRAL_DELEGACION,
            defaults={'valor': 80},
        )
        period = Periodo.objects.create(
            nombre='Período de umbral', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        item = Item.objects.create(
            nombre='Ítem de umbral',
            ponderacion='99.9',
        )
        Desempeno.objects.create(
            usuario=self.user, item=item, periodo=period, meta=10,
        )

        personal_response = self.client.get(
            reverse('funcionario:home'), {'periodo': period.pk},
        )
        personal_classification = personal_response.context['clasificacion_umbral']

        delegate = create_user(
            email='delegado-umbral@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
            delegacion=self.delegation,
        )
        delegate_client = Client()
        delegate_client.force_login(delegate)
        delegate_response = delegate_client.get(
            reverse('delegado:resumen'), {'periodo': period.pk},
        )
        delegate_row = delegate_response.context['funcionarios'][0]

        self.assertEqual(personal_classification, 'bajo')
        self.assertEqual(delegate_row['clasificacion_umbral'], personal_classification)

    def test_personal_dashboard_does_not_classify_employee_without_items(self):
        response = self.client.get(reverse('funcionario:home'))

        self.assertEqual(response.context['clasificacion_umbral'], None)
        self.assertContains(response, 'Sin ítems asignados')

    def create_neighbor(self, nombre, telefono, delegation=None, **fields):
        delegation = delegation or self.delegation
        territory = Territorio.objects.create(
            nombre=f'Territorio {nombre}',
            delegacion=delegation,
        )
        junta = self.create_junta(
            f'Junta {nombre}',
            delegation=delegation,
            territory=territory,
        )
        cargo = CargoJv.objects.create(
            nombre=f'Cargo {nombre}',
            permisos='Administrar junta',
            junta_vecino=junta,
        )
        return Vecino.objects.create(
            nombre=nombre,
            telefono=telefono,
            territorio=territory,
            delegacion=delegation,
            junta_vecino=junta,
            cargo_jv=cargo,
            **fields,
        )

    def create_junta(self, nombre, delegation=None, territory=None, **fields):
        delegation = delegation or self.delegation
        territory = territory or self.territory
        return JuntaVecinos.objects.create(
            nombre=nombre,
            domicilio_legal='Domicilio legal',
            territorio=territory,
            delegacion=delegation,
            numero_rpj=JuntaVecinos.objects.count() + 1,
            **fields,
        )

    def create_commitment(self, **fields):
        return Compromiso.objects.create(
            tipo=self.attention_type,
            subtipo=self.subattention,
            **fields,
        )

    def test_neighbors_list_defaults_to_active_and_supports_inactive_filter(self):
        self.create_neighbor('Vecino activo', '912345678')
        self.create_neighbor('Vecino inactivo', '923456789', activo=False)

        response = self.client.get(reverse('funcionario:vecinos'))
        self.assertContains(response, 'Vecino activo')
        self.assertNotContains(response, 'Vecino inactivo')

        response = self.client.get(reverse('funcionario:vecinos'), {'inactivos': '1'})
        self.assertContains(response, 'Vecino activo')
        self.assertContains(response, 'Vecino inactivo')
        form_response = self.client.get(reverse('funcionario:vecino_nuevo'))
        self.assertContains(form_response, 'list="territorios-usados"')

    def test_neighbor_crud_warns_on_duplicate_phone_and_validates_fields(self):
        original = self.create_neighbor('Vecino original', '9 123 456 78')
        territory_id = original.territorio_id
        junta_id = original.junta_vecino_id
        cargo_id = original.cargo_jv_id
        response = self.client.post(reverse('funcionario:vecino_nuevo'), {
            'nombre': 'Vecino repetido',
            'telefono': '912345678',
            'direccion': '',
            'territorio': territory_id,
            'junta_vecino': junta_id,
            'cargo_jv': cargo_id,
            'delegacion': self.delegation.pk,
            'solicitante': '',
            'activo': 'on',
        })
        self.assertRedirects(response, reverse('funcionario:vecinos'))
        self.assertTrue(any('ya existe otro vecino' in str(message) for message in get_messages(response.wsgi_request)))

        invalid = self.client.post(reverse('funcionario:vecino_nuevo'), {
            'nombre': 'A', 'telefono': '123', 'direccion': '',
            'territorio': '', 'delegacion': self.delegation.pk,
            'solicitante': '', 'activo': 'on',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(Vecino.objects.filter(nombre='A').count(), 0)

    def test_neighbor_scope_is_limited_to_delegation_and_admin_sees_all(self):
        other_delegation = Delegacion.objects.create(nombre='Otra delegación vecinal')
        foreign_neighbor = self.create_neighbor(
            'Vecino extranjero', '934567890', delegation=other_delegation,
        )
        self.assertEqual(
            self.client.get(reverse('funcionario:vecinos')).context['page_obj'].paginator.count,
            0,
        )
        self.assertEqual(
            self.client.get(reverse('funcionario:vecino_editar', args=[foreign_neighbor.pk])).status_code,
            404,
        )

        admin = create_user(
            email='administrador-vecinos@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('funcionario:vecinos'))
        self.assertContains(response, 'Vecino extranjero')

    def test_deleting_neighbor_sets_solicitante_link_null_without_deleting_solicitante(self):
        solicitante = Beneficiado.objects.create(
            nombre='Solicitante',
            apellido='Vinculado',
            telefono=945678901,
        )
        vecino = self.create_neighbor(
            'Vecino vinculado', '945678901', solicitante=solicitante,
        )
        vecino.delete()
        solicitante.refresh_from_db()
        self.assertTrue(Beneficiado.objects.filter(pk=solicitante.pk).exists())
        self.assertFalse(Vecino.objects.filter(pk=vecino.pk).exists())

    def _junta_payload(self, **overrides):
        payload = {
            'nombre': 'Junta Nueva',
            'domicilio_legal': 'Calle Legal 123',
            'territorio': self.territory.pk,
            'delegacion': self.delegation.pk,
            'socios_activos': '10',
            'fecha_constitucion': '2020-01-01T00:00',
            'numero_rpj': '1',
            'fecha_ingreso': '2020-02-01T00:00',
            'numero_registro': '1',
        }
        payload.update(overrides)
        return payload

    def test_vecino_junta_duplicate_is_rejected_without_server_error(self):
        first = self.create_junta('Junta Uno')
        second = self.create_junta('Junta Dos')
        vecino = self.create_neighbor('Vecino con juntas', '956789012')
        VecinoJunta.objects.create(vecino=vecino, junta=first)
        VecinoJunta.objects.create(vecino=vecino, junta=second)

        response = self.client.post(
            reverse('funcionario:vecino_editar', args=[vecino.pk]),
            {
                'nombre': vecino.nombre, 'telefono': vecino.telefono,
                'direccion': '', 'territorio': vecino.territorio_id,
                'delegacion': self.delegation.pk, 'solicitante': '',
                'activo': 'on', 'junta_vecino': second.pk,
                'cargo_jv': vecino.cargo_jv_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ya está relacionado con esa junta')
        self.assertEqual(VecinoJunta.objects.filter(vecino=vecino).count(), 2)

    def test_vecino_form_changes_only_displayed_membership_and_warns_on_others(self):
        first = self.create_junta('Junta Principal')
        second = self.create_junta('Junta Secundaria')
        vecino = self.create_neighbor('Vecino dirigente', '967890123')
        VecinoJunta.objects.create(vecino=vecino, junta=first)
        VecinoJunta.objects.create(vecino=vecino, junta=second)

        response = self.client.post(
            reverse('funcionario:vecino_editar', args=[vecino.pk]),
            {
                'nombre': vecino.nombre, 'telefono': vecino.telefono,
                'direccion': '', 'territorio': vecino.territorio_id,
                'delegacion': self.delegation.pk, 'solicitante': '',
                'activo': 'on', 'junta_vecino': first.pk,
                'cargo_jv': vecino.cargo_jv_id,
            },
        )
        self.assertRedirects(response, reverse('funcionario:vecinos'))
        self.assertTrue(any('las demás se conservaron' in str(message) for message in get_messages(response.wsgi_request)))
        self.assertEqual(VecinoJunta.objects.filter(vecino=vecino).count(), 2)
        self.assertTrue(VecinoJunta.objects.get(vecino=vecino, junta=first).es_dirigente)
        self.assertTrue(VecinoJunta.objects.filter(vecino=vecino, junta=second).exists())

    def test_junta_validations_and_personality_number_warning(self):
        admin = create_user(
            email='admin-juntas@sgr.test', password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='administrador'),
        )
        self.client.force_login(admin)
        invalid = self.client.post(
            reverse('funcionario:junta_nueva'),
            self._junta_payload(socios_activos='-1', fecha_ingreso='2019-01-01T00:00'),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(JuntaVecinos.objects.exists())

        created = self.client.post(reverse('funcionario:junta_nueva'), self._junta_payload())
        self.assertRedirects(created, reverse('funcionario:juntas'))
        warning = self.client.post(
            reverse('funcionario:junta_nueva'),
            self._junta_payload(nombre='Junta Duplicada', numero_rpj='1'),
        )
        self.assertRedirects(warning, reverse('funcionario:juntas'))
        self.assertTrue(any('número de personalidad jurídica' in str(message) for message in get_messages(warning.wsgi_request)))

    def test_employee_can_delete_only_unrelated_juntas_and_deactivate_related_ones(self):
        unrelated = self.create_junta('Junta Eliminable')
        response = self.client.post(reverse('funcionario:junta_eliminar', args=[unrelated.pk]))
        self.assertRedirects(response, reverse('funcionario:juntas'))
        self.assertFalse(JuntaVecinos.objects.filter(pk=unrelated.pk).exists())

        related = self.create_junta('Junta Relacionada')
        vecino = self.create_neighbor('Vecino relacionado', '978901234')
        VecinoJunta.objects.create(vecino=vecino, junta=related)
        response = self.client.post(reverse('funcionario:junta_eliminar', args=[related.pk]))
        self.assertRedirects(response, reverse('funcionario:juntas'))
        self.assertTrue(JuntaVecinos.objects.filter(pk=related.pk).exists())

        response = self.client.post(reverse('funcionario:junta_desactivar', args=[related.pk]))
        self.assertRedirects(response, reverse('funcionario:juntas'))
        self.assertFalse(JuntaVecinos.objects.get(pk=related.pk).activo)

    def test_delegate_cannot_create_junta_yet(self):
        delegate = create_user(
            email='delegado-sin-juntas@sgr.test', password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'), delegacion=self.delegation,
        )
        self.client.force_login(delegate)
        response = self.client.get(reverse('funcionario:junta_nueva'))
        self.assertEqual(response.status_code, 403)

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
        other_type = Tipo.objects.create(
            nombre='Otro tipo',
        )
        other_subattention = SubAtencion.objects.create(
            nombre='Otra sub atención',
            tipo=other_type,
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
        applicant = Beneficiado.objects.create(
            nombre='Persona',
            apellido='Solicitante',
            telefono=12345678,
        )
        Beneficiado.objects.create(
            nombre='Otra',
            apellido='Beneficiada',
            telefono=87654321,
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
        self.subattention.estado = SubAtencion.Estado.DESACTIVADO
        self.subattention.save(update_fields=['estado'])
        active_subattention = SubAtencion.objects.create(
            nombre='Orientación activa',
            tipo=self.attention_type,
        )
        inactive_type = Tipo.objects.create(
            nombre='Tipo inactivo',
            estado=Tipo.Estado.DESACTIVADO,
        )
        SubAtencion.objects.create(
            nombre='Sub atención inactiva',
            tipo=inactive_type,
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
        foreign_applicant = Beneficiado.objects.create(
            nombre='Persona',
            apellido='de otra delegación',
            telefono=99999999,
        )

        response = self.client.post(reverse('funcionario:atencion_social'), {
            'action': 'crear_caso',
            'solicitante_registrado': foreign_applicant.pk,
            'identificador': foreign_applicant.pk,
            'nombre_solicitante': foreign_applicant.nombre,
            'tipo_atencion_catalogo': self.attention_type.pk,
            'sub_atencion': self.subattention.pk,
            'descripcion': 'Solicitud de orientación familiar',
            'resultado': '',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertEqual(Beneficiado.objects.count(), 1)

    def test_switching_delegation_scopes_cases_and_solicitantes(self):
        self.create_case()
        second_delegation = Delegacion.objects.create(
            nombre='Delegación secundaria de atención',
        )
        UsuarioDelegacion.objects.create(
            usuario=self.user,
            delegacion=second_delegation,
        )
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
        user = create_user(
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
        self.assertFalse(Beneficiado.objects.exists())

    def test_cancel_does_not_create_case_or_applicant(self):
        response = self.client.get(reverse('funcionario:atencion_social'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertFalse(Beneficiado.objects.exists())

    def test_user_cannot_add_attention_to_another_users_case(self):
        case_record = AtencionSocial.objects.create(
            usuario=self.user,
            tipo_atencion='Caso privado',
            fecha='2026-10-20',
        )
        case = CasoSocial.objects.create(atencion_social=case_record)
        other_user = create_user(
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
        user = create_user(
            email='delegado-social@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='delegado'),
        )
        self.client.force_login(user)

        for route in (
            'funcionario:home',
            'funcionario:gestion_actividades',
            'funcionario:atencion_social',
            'funcionario:agenda_colectiva',
            'funcionario:cumplimiento',
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)

    def test_assigned_employee_can_update_commitment_with_history(self):
        delegation = Delegacion.objects.create(nombre='Delegación de agenda')
        UsuarioDelegacion.objects.filter(
            usuario=self.user,
            fecha_fin__isnull=True,
        ).update(fecha_fin=timezone.now())
        UsuarioDelegacion.objects.create(
            usuario=self.user,
            delegacion=delegation,
        )
        period = Periodo.objects.create(
            nombre='Agenda de funcionario',
            fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31',
        )
        agenda = Agenda.objects.create(delegacion=delegation, periodo=period)
        commitment = self.create_commitment(
            agenda=agenda,
            descripcion='Compromiso asignado',
            fecha='2026-10-25',
        )
        commitment.responsable.add(self.user)

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
        UsuarioDelegacion.objects.filter(
            usuario=self.user,
            fecha_fin__isnull=True,
        ).update(fecha_fin=timezone.now())
        UsuarioDelegacion.objects.create(
            usuario=self.user,
            delegacion=delegation,
        )
        period = Periodo.objects.create(
            nombre='Agenda restringida',
            fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31',
        )
        agenda = Agenda.objects.create(delegacion=delegation, periodo=period)
        commitment = self.create_commitment(
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

    def test_employee_can_create_and_edit_commitment_without_reassigning_responsibles(self):
        period = Periodo.objects.create(
            nombre='Agenda de ingreso', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        response = self.client.post(reverse('funcionario:compromiso_nuevo'), {
            'periodo': period.pk,
            'descripcion': 'Compromiso propio',
            'solicitante': 'Vecindario',
            'territorio': 'Norte',
            'fecha': '2026-10-20',
            'observaciones': 'Inicial',
        })
        self.assertRedirects(response, reverse('funcionario:agenda_colectiva'))
        commitment = Compromiso.objects.get(descripcion='Compromiso propio')
        self.assertEqual(list(commitment.responsable.values_list('pk', flat=True)), [self.user.pk])

        other_user = create_user(
            email='responsable-delegado@sgr.test',
            password='Sgr-Test-Password-418!',
            cargo=self.user.cargo,
            delegacion=self.delegation,
        )
        commitment.responsable.add(other_user)
        response = self.client.post(
            reverse('funcionario:compromiso_editar', args=[commitment.pk]),
            {
                'descripcion': 'Compromiso modificado',
                'solicitante': 'Vecindario actualizado',
                'territorio': 'Sur',
                'fecha': '2026-10-21',
                'observaciones': 'Modificado',
            },
        )
        self.assertRedirects(response, reverse('funcionario:agenda_colectiva'))
        commitment.refresh_from_db()
        self.assertEqual(commitment.descripcion, 'Compromiso modificado')
        self.assertEqual(set(commitment.responsable.values_list('pk', flat=True)), {self.user.pk, other_user.pk})

    def test_employee_can_upload_commitment_evidence_and_supervisor_inbox_opens(self):
        period = Periodo.objects.create(
            nombre='Agenda con evidencia', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        agenda = Agenda.objects.create(delegacion=self.delegation, periodo=period)
        commitment = self.create_commitment(
            agenda=agenda, descripcion='Compromiso con respaldo', fecha='2026-10-20',
        )
        commitment.responsable.add(self.user)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('funcionario:compromiso_evidencia', args=[commitment.pk]),
                {'evidencia': SimpleUploadedFile(
                    'compromiso.pdf', b'%PDF-1.4\nrespaldo', content_type='application/pdf',
                )},
            )
            self.assertRedirects(response, reverse('funcionario:agenda_colectiva'))
            evidence = Evidencia.objects.get(compromiso=commitment)
            self.assertIsNone(evidence.registro_id)
            original_code = evidence.codigo
            evidence.codigo = uuid4()
            with self.assertRaises(ValueError):
                evidence.save()
            evidence.refresh_from_db()
            response = self.client.get(reverse('funcionario:agenda_colectiva'))
            self.assertContains(response, 'Edición general bloqueada')
            self.assertTrue(Historial.objects.filter(
                entidad_afectada=f'Evidencia:{evidence.pk}',
                accion='Cargar evidencia de compromiso',
            ).exists())

            UsuarioCargo.objects.filter(
                usuario=self.user,
                fecha_fin__isnull=True,
            ).update(fecha_fin=timezone.now())
            UsuarioCargo.objects.create(
                usuario=self.user,
                cargo=Cargo.objects.create(nombre='supervisor'),
            )
            response = self.client.get(reverse('supervisor:home'))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Compromiso')
            evidence.refresh_from_db()
            self.assertEqual(evidence.codigo, original_code)

    def test_employee_cannot_edit_commitment_outside_active_delegation(self):
        other_delegation = Delegacion.objects.create(nombre='Delegación ajena')
        period = Periodo.objects.create(
            nombre='Agenda ajena', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        agenda = Agenda.objects.create(delegacion=other_delegation, periodo=period)
        commitment = self.create_commitment(
            agenda=agenda, descripcion='Compromiso fuera de alcance', fecha='2026-10-20',
        )
        commitment.responsable.add(self.user)

        response = self.client.get(
            reverse('funcionario:compromiso_editar', args=[commitment.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_employee_cannot_edit_or_upload_evidence_for_unassigned_commitment(self):
        period = Periodo.objects.create(
            nombre='Agenda no asignada', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        agenda = Agenda.objects.create(delegacion=self.delegation, periodo=period)
        commitment = self.create_commitment(
            agenda=agenda, descripcion='Compromiso no asignado', fecha='2026-10-20',
        )

        edit_response = self.client.get(
            reverse('funcionario:compromiso_editar', args=[commitment.pk]),
        )
        evidence_response = self.client.get(
            reverse('funcionario:compromiso_evidencia', args=[commitment.pk]),
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(evidence_response.status_code, 404)

    def test_employee_commitment_operations_are_blocked_in_closed_period(self):
        closed_period = Periodo.objects.create(
            nombre='Agenda cerrada', fecha_inicio='2026-07-01',
            fecha_fin='2026-09-30', estado=Periodo.Estado.CERRADO,
        )
        create_response = self.client.post(reverse('funcionario:compromiso_nuevo'), {
            'periodo': closed_period.pk,
            'descripcion': 'No debe crearse',
            'fecha': '2026-09-20',
        })
        self.assertEqual(create_response.status_code, 200)
        self.assertFalse(Compromiso.objects.filter(descripcion='No debe crearse').exists())

        agenda = Agenda.objects.create(delegacion=self.delegation, periodo=closed_period)
        commitment = self.create_commitment(
            agenda=agenda, descripcion='Compromiso cerrado', fecha='2026-09-20',
        )
        commitment.responsable.add(self.user)
        edit_response = self.client.get(
            reverse('funcionario:compromiso_editar', args=[commitment.pk]),
        )
        evidence_response = self.client.post(
            reverse('funcionario:compromiso_evidencia', args=[commitment.pk]),
            {'evidencia': SimpleUploadedFile(
                'cerrado.pdf', b'%PDF-1.4\nrespaldo', content_type='application/pdf',
            )},
        )

        self.assertRedirects(edit_response, reverse('funcionario:agenda_colectiva'))
        self.assertRedirects(evidence_response, reverse('funcionario:agenda_colectiva'))
        self.assertFalse(Evidencia.objects.filter(compromiso=commitment).exists())

    def test_employee_rejects_invalid_commitment_evidence_file(self):
        period = Periodo.objects.create(
            nombre='Agenda archivo inválido', fecha_inicio='2026-10-01',
            fecha_fin='2026-12-31', estado=Periodo.Estado.ABIERTO,
        )
        agenda = Agenda.objects.create(delegacion=self.delegation, periodo=period)
        commitment = self.create_commitment(
            agenda=agenda, descripcion='Compromiso archivo inválido', fecha='2026-10-20',
        )
        commitment.responsable.add(self.user)

        response = self.client.post(
            reverse('funcionario:compromiso_evidencia', args=[commitment.pk]),
            {'evidencia': SimpleUploadedFile(
                'archivo.exe', b'contenido no permitido', content_type='application/octet-stream',
            )},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Evidencia.objects.filter(compromiso=commitment).exists())
        self.assertContains(response, 'No se pudo cargar la evidencia')

    def test_administrator_can_access_employee_commitment_routes(self):
        UsuarioCargo.objects.filter(
            usuario=self.user,
            fecha_fin__isnull=True,
        ).update(fecha_fin=timezone.now())
        UsuarioCargo.objects.create(
            usuario=self.user,
            cargo=Cargo.objects.create(nombre='administrador'),
        )

        response = self.client.get(reverse('funcionario:compromiso_nuevo'))

        self.assertEqual(response.status_code, 200)


class TargetSchemaFuncionarioModelTests(TestCase):
    def setUp(self):
        self.delegacion = Delegacion.objects.create(nombre='Delegación para territorio')
        self.territorio = Territorio.objects.create(
            nombre='Territorio',
            delegacion=self.delegacion,
        )
        self.junta = JuntaVecinos.objects.create(
            nombre='Junta para cargo',
            domicilio_legal='Domicilio',
            territorio=self.territorio,
            delegacion=self.delegacion,
            fecha_constitucion='2020-01-01',
            numero_rpj=1,
            fecha_ingreso='2020-02-01',
            numero_registro=1,
        )

    def test_territorio_creation_and_delegacion_relation(self):
        territorio = Territorio.objects.create(
            nombre='Sector norte',
            delegacion=self.delegacion,
        )

        territorio.refresh_from_db()
        self.assertEqual(territorio.delegacion, self.delegacion)
        self.assertEqual(
            self.delegacion.territorios.get(pk=territorio.pk),
            territorio,
        )

    def test_delegacion_with_territorio_is_protected(self):
        Territorio.objects.create(nombre='Sector protegido', delegacion=self.delegacion)

        with self.assertRaises(ProtectedError):
            self.delegacion.delete()

    def test_cargo_jv_creation_and_junta_relation(self):
        cargo = CargoJv.objects.create(
            nombre='Tesorero',
            permisos='Administrar fondos',
            junta_vecino=self.junta,
        )

        cargo.refresh_from_db()
        self.assertEqual(cargo.junta_vecino, self.junta)
        self.assertEqual(self.junta.cargos.get(), cargo)

    def test_junta_with_cargo_is_protected(self):
        CargoJv.objects.create(
            nombre='Secretario',
            permisos='Registrar actas',
            junta_vecino=self.junta,
        )

        with self.assertRaises(ProtectedError):
            self.junta.delete()

    def test_beneficiado_accepts_null_email_and_preserves_phone_text(self):
        beneficiado = Beneficiado.objects.create(
            nombre='Ana',
            apellido='Pérez',
            telefono='+560912345678',
            email=None,
        )

        beneficiado.refresh_from_db()
        self.assertIsNone(beneficiado.email)
        self.assertEqual(beneficiado.telefono, '+560912345678')

    def test_new_rows_receive_distinct_primary_keys(self):
        first = Beneficiado.objects.create(
            nombre='María', apellido='Uno', telefono='0012345',
        )
        second = Beneficiado.objects.create(
            nombre='María', apellido='Dos', telefono='0012345',
        )

        self.assertNotEqual(first.pk, second.pk)
