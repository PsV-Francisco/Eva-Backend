from django import forms
from django.db.models import Q
from AdminApp.models import Catalogo, SubAtencion, TipoAtencion
from CoordinadorApp.models import Periodo
from CoordinadorApp.models import Funcion, Item
from FuncionarioApp.models import (
    AtencionSocial,
    GestionAtencion,
    Registro,
    Solicitante,
)
from config.forms import BootstrapFormMixin
from SupervisorApp.files import validate_evidence_file


class RegistroForm(BootstrapFormMixin, forms.ModelForm):
    evidencia = forms.FileField(
        label='Archivo de evidencia',
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,application/pdf'}),
    )

    class Meta:
        model = Registro
        fields = (
            'fecha', 'periodo', 'item', 'catalogo', 'descripcion', 'accion', 'contacto',
            'telefono', 'incluir_en_agenda',
        )
        labels = {
            'fecha': 'Fecha de actividad',
            'periodo': 'Período',
            'item': 'Ítem de medición',
            'catalogo': 'Clasificación del servicio',
            'descripcion': 'Actividad o solicitud',
            'accion': 'Acción realizada',
            'contacto': 'Contacto',
            'telefono': 'Teléfono',
            'incluir_en_agenda': 'Relacionar con la agenda colectiva',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'accion': forms.Textarea(attrs={'rows': 3}),
            'contacto': forms.TextInput(attrs={'autocomplete': 'name'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['periodo'].queryset = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO)
        catalogs = Catalogo.objects.filter(
            estado=Catalogo.Estado.ACTIVO,
        )
        if self.instance.pk and self.instance.catalogo_id:
            catalogs = Catalogo.objects.filter(
                Q(estado=Catalogo.Estado.ACTIVO)
                | Q(pk=self.instance.catalogo_id),
            )
        self.fields['catalogo'].queryset = catalogs.order_by(
            'actividad', 'servicio', 'tipo', 'subtipo',
        )
        if user and user.cargo_id and user.cargo.funciones_id:
            items = Item.objects.filter(
                funcion_id=user.cargo.funciones_id,
                estado=Item.Estado.ACTIVO,
                funcion__estado=Funcion.Estado.ACTIVO,
            )
            if self.instance.pk and self.instance.item_id:
                items = (items | Item.objects.filter(
                    pk=self.instance.item_id,
                )).distinct()
            self.fields['item'].queryset = items
        else:
            self.fields['item'].queryset = Item.objects.none()

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        if uploaded_file:
            return validate_evidence_file(uploaded_file)
        return uploaded_file


class CasoSocialForm(BootstrapFormMixin, forms.ModelForm):
    solicitante_registrado = forms.ModelChoiceField(
        queryset=Solicitante.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )
    identificador = forms.CharField(
        label='Identificador del solicitante',
        max_length=32,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'data-solicitante-identificador': '',
        }),
    )
    nombre_solicitante = forms.CharField(
        label='Nombre del solicitante',
        max_length=160,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'data-solicitante-nombre': '',
        }),
    )
    tipo_atencion_catalogo = forms.ModelChoiceField(
        label='Tipo de Atención',
        queryset=TipoAtencion.objects.none(),
    )
    sub_atencion = forms.ModelChoiceField(
        label='Sub Atención',
        queryset=SubAtencion.objects.none(),
    )
    descripcion = forms.CharField(
        label='Descripción de la atención',
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    class Meta:
        model = AtencionSocial
        fields = ('resultado', 'observaciones')
        labels = {
            'resultado': 'Antecedentes del caso',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'resultado': forms.Textarea(attrs={'rows': 3}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, delegation=None, **kwargs):
        self.delegation = delegation
        super().__init__(*args, **kwargs)
        self.fields['solicitante_registrado'].queryset = (
            Solicitante.objects.filter(delegacion=delegation)
            if delegation else Solicitante.objects.none()
        )
        self.fields['tipo_atencion_catalogo'].queryset = TipoAtencion.objects.filter(
            estado=TipoAtencion.Estado.ACTIVO,
        )
        selected_type_id = (
            self.data.get('tipo_atencion_catalogo')
            or self.initial.get('tipo_atencion_catalogo')
        )
        self.fields['sub_atencion'].queryset = SubAtencion.objects.filter(
            tipo_atencion_id=selected_type_id,
            estado=SubAtencion.Estado.ACTIVO,
        ) if selected_type_id else SubAtencion.objects.none()

    def clean_identificador(self):
        return self.cleaned_data['identificador'].strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get('identificador')
        name = cleaned_data.get('nombre_solicitante', '').strip()
        selected_applicant = cleaned_data.get('solicitante_registrado')
        applicant = selected_applicant

        if selected_applicant and identifier != selected_applicant.identificador:
            self.add_error(
                'solicitante_registrado',
                'El solicitante seleccionado no coincide con el identificador.',
            )
            applicant = None
        elif identifier and self.delegation and not applicant:
            applicant = Solicitante.objects.filter(
                delegacion=self.delegation,
                identificador=identifier,
            ).first()

        if applicant and name.casefold() != applicant.nombre.casefold():
            self.add_error(
                'nombre_solicitante',
                'Selecciona el solicitante encontrado para usar su nombre registrado.',
            )
            applicant = None
        cleaned_data['resolved_solicitante'] = applicant
        return cleaned_data

    def resolve_solicitante(self):
        applicant = self.cleaned_data['resolved_solicitante']
        if applicant:
            return applicant
        applicant, _ = Solicitante.objects.get_or_create(
            delegacion=self.delegation,
            identificador=self.cleaned_data['identificador'],
            defaults={'nombre': self.cleaned_data['nombre_solicitante'].strip()},
        )
        return applicant


class GestionAtencionForm(BootstrapFormMixin, forms.ModelForm):
    evidencia = forms.FileField(
        label='Evidencia de la atención',
        widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,application/pdf'}),
    )

    class Meta:
        model = GestionAtencion
        fields = ('fecha', 'observaciones')
        labels = {'fecha': 'Fecha de atención', 'observaciones': 'Detalle de la atención'}
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_evidencia(self):
        return validate_evidence_file(self.cleaned_data['evidencia'])