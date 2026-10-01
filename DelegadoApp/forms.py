from django import forms

from AdminApp.models import Usuario
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Compromiso
from config.forms import BootstrapFormMixin


class CompromisoForm(BootstrapFormMixin, forms.ModelForm):
    periodo = forms.ModelChoiceField(
        queryset=Periodo.objects.filter(estado=Periodo.Estado.ABIERTO),
        label='Período de agenda',
    )

    class Meta:
        model = Compromiso
        fields = ('periodo', 'descripcion', 'solicitante', 'territorio', 'fecha', 'responsables', 'estado', 'observaciones')
        labels = {
            'descripcion': 'Compromiso',
            'solicitante': 'Solicitante',
            'territorio': 'Territorio',
            'fecha': 'Fecha comprometida',
            'responsables': 'Responsables',
            'estado': 'Estado',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
            'responsables': forms.SelectMultiple(attrs={'size': 4}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if user.delegacion_id:
            self.fields['responsables'].queryset = Usuario.objects.filter(
                delegacion_id=user.delegacion_id, is_active=True,
            ).order_by('email')
        else:
            self.fields['responsables'].queryset = Usuario.objects.none()
        self.fields['responsables'].help_text = 'Selecciona al menos un responsable.'


class CompromisoEstadoForm(BootstrapFormMixin, forms.Form):
    estado = forms.ChoiceField(choices=Compromiso.Estado.choices, label='Actualizar estado')