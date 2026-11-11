from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils import timezone

from AdminApp.models import Cargo, Delegacion, UsuarioCargo, UsuarioDelegacion
from CoordinadorApp.models import AtencionSocial, GestionAtencion
from DelegadoApp.forms import CompromisoForm
from FuncionarioApp.forms import AtencionSocialForm, RegistroForm
from FuncionarioApp.models import Beneficiado, Subtipo, Tipo
from SupervisorApp.models import Evidencia
from SupervisorApp.views import _evidencias_visibles


class CurrentModelFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='migration-contract@example.test',
            password='test-password',
        )
        self.delegation = Delegacion.objects.create(nombre='Delegación de prueba')
        self.position = Cargo.objects.create(nombre='funcionario')
        UsuarioCargo.objects.create(
            usuario=self.user,
            cargo=self.position,
            fecha_inicio=timezone.now(),
        )
        UsuarioDelegacion.objects.create(
            usuario=self.user,
            delegacion=self.delegation,
            fecha_inicio=timezone.now(),
        )

    def test_type_subtype_fields_are_declared_on_current_forms(self):
        for form_class in (AtencionSocialForm, RegistroForm, CompromisoForm):
            with self.subTest(form=form_class.__name__):
                form = (
                    form_class(user=self.user, delegation=self.delegation)
                    if form_class is CompromisoForm
                    else form_class()
                )
                self.assertIn('tipo', form.fields)
                self.assertIn('subtipo', form.fields)

    def test_social_attention_creates_linked_default_type_subtype_and_management(self):
        beneficiary = Beneficiado.objects.create(
            nombre='Ana',
            apellido='Prueba',
            telefono=12345678,
        )
        now = timezone.localtime()
        form = AtencionSocialForm(data={
            'beneficiado': beneficiary.pk,
            'fecha': now.strftime('%Y-%m-%dT%H:%M'),
            'resultado': 'Orientación entregada',
            'observaciones': '',
            'numero_gestion': 2,
            'fecha_gestion': timezone.localdate().isoformat(),
            'observaciones_gestion': 'Seguimiento',
        }, files={
            'evidencia': SimpleUploadedFile(
                'atencion.pdf',
                b'%PDF-1.4 test',
                content_type='application/pdf',
            ),
        })

        self.assertTrue(form.is_valid(), form.errors)
        gestion, atencion = form.save(autor=self.user)

        self.assertEqual(AtencionSocial.objects.get(), atencion)
        self.assertEqual(gestion.numero_gestion, 2)
        self.assertEqual(atencion.beneficiado, beneficiary)
        self.assertEqual(atencion.tipo.nombre, 'Sin tipo')
        self.assertEqual(atencion.subtipo.nombre, 'Sin subtipo')
        self.assertEqual(atencion.subtipo.tipo, atencion.tipo)

    def test_social_attention_form_offers_active_legacy_types_and_subtypes(self):
        tipo = Tipo.objects.create(
            nombre='Tipo legado activo',
            estado='Activo',
        )
        subtipo = Subtipo.objects.create(
            nombre='Subtipo legado activo',
            tipo=tipo,
            estado='ACTIVO',
        )
        inactive_type = Tipo.objects.create(
            nombre='Tipo desactivado',
            estado=Tipo.Estado.DESACTIVADO,
        )
        inactive_subtype = Subtipo.objects.create(
            nombre='Subtipo desactivado',
            tipo=tipo,
            estado=Subtipo.Estado.DESACTIVADO,
        )

        form = AtencionSocialForm()

        self.assertIn(tipo, form.fields['tipo'].queryset)
        self.assertIn(subtipo, form.fields['subtipo'].queryset)
        self.assertNotIn(inactive_type, form.fields['tipo'].queryset)
        self.assertNotIn(inactive_subtype, form.fields['subtipo'].queryset)

    def test_social_attention_can_create_a_new_beneficiary(self):
        now = timezone.localtime()
        form = AtencionSocialForm(data={
            'beneficiado': '',
            'nombre': 'Pedro',
            'apellido': 'Nuevo',
            'telefono': '12345678',
            'email': 'pedro@example.test',
            'fecha': now.strftime('%Y-%m-%dT%H:%M'),
            'resultado': '',
            'observaciones': '',
            'numero_gestion': 1,
            'fecha_gestion': timezone.localdate().isoformat(),
            'observaciones_gestion': '',
        }, files={
            'evidencia': SimpleUploadedFile(
                'atencion.pdf',
                b'%PDF-1.4 test',
                content_type='application/pdf',
            ),
        })

        self.assertTrue(form.is_valid(), form.errors)
        gestion, atencion = form.save(autor=self.user)

        self.assertEqual(AtencionSocial.objects.get(), atencion)
        self.assertEqual(gestion.numero_gestion, 1)
        self.assertEqual(atencion.beneficiado.nombre, 'Pedro')
        self.assertEqual(atencion.beneficiado.email, 'pedro@example.test')

    def test_social_evidence_is_visible_through_active_user_delegation(self):
        beneficiary = Beneficiado.objects.create(
            nombre='Ana',
            apellido='Prueba',
            telefono=12345678,
        )
        tipo = Tipo.objects.create(nombre='Tipo de evidencia')
        subtipo = Subtipo.objects.create(nombre='Subtipo de evidencia', tipo=tipo)
        gestion = GestionAtencion.objects.create(
            numero_gestion=1,
            fecha=timezone.localdate(),
        )
        atencion = AtencionSocial.objects.create(
            fecha=timezone.now(),
            autor=self.user,
            beneficiado=beneficiary,
            tipo=tipo,
            subtipo=subtipo,
            gestion_atencion=gestion,
        )
        Evidencia.objects.create(
            archivo='atencion.pdf',
            gestion_atencion=gestion,
            autor=self.user,
        )
        request = RequestFactory().get('/')
        request.user = self.user
        request.session = {}
        request._active_delegation = self.delegation

        self.assertEqual(
            list(_evidencias_visibles(request).values_list('pk', flat=True)),
            list(Evidencia.objects.filter(gestion_atencion=atencion.gestion_atencion).values_list('pk', flat=True)),
        )

    def test_commitment_responsibles_are_scoped_to_active_delegation_assignments(self):
        inactive_user = get_user_model().objects.create_user(
            email='inactive-assignment@example.test',
            password='test-password',
        )
        UsuarioDelegacion.objects.create(
            usuario=inactive_user,
            delegacion=self.delegation,
            fecha_inicio=timezone.now(),
            fecha_fin=timezone.now(),
        )

        form = CompromisoForm(user=self.user, delegation=self.delegation)

        self.assertEqual(
            list(form.fields['responsable'].queryset),
            [self.user],
        )
