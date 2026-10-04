from django import forms
from pathlib import Path

from AdminApp.models import Catalogo
from CoordinadorApp.models import Periodo
from CoordinadorApp.models import Item
from FuncionarioApp.models import Registro
from config.forms import BootstrapFormMixin


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
            extension = Path(uploaded_file.name).suffix.lower()
            if extension not in {'.jpg', '.jpeg', '.png', '.pdf'}:
                raise forms.ValidationError('Usa una imagen JPG/PNG o un documento PDF.')
            if uploaded_file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('El archivo no puede superar los 5 MB.')
        return uploaded_file