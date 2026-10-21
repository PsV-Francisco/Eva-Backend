from django import forms
from AdminApp.models import Catalogo
from CoordinadorApp.models import Periodo
from CoordinadorApp.models import Item
from FuncionarioApp.models import AtencionSocial, GestionAtencion, Registro
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
        self.fields['catalogo'].queryset = Catalogo.objects.order_by(
            'actividad', 'servicio', 'tipo', 'subtipo',
        )
        if user and user.cargo_id and user.cargo.funciones_id:
            self.fields['item'].queryset = Item.objects.filter(funcion_id=user.cargo.funciones_id)
        else:
            self.fields['item'].queryset = Item.objects.none()

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        if uploaded_file:
            return validate_evidence_file(uploaded_file)
        return uploaded_file


class CasoSocialForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AtencionSocial
        fields = ('tipo_atencion', 'fecha', 'resultado', 'observaciones')
        labels = {
            'tipo_atencion': 'Nombre o motivo del caso',
            'fecha': 'Fecha de apertura',
            'resultado': 'Antecedentes del caso',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'resultado': forms.Textarea(attrs={'rows': 3}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }


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