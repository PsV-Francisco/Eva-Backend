from django import forms
from django.db.models import Q

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

    def __init__(self, *args, user, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        delegation_id = (
            delegation.pk if delegation else user.delegacion_id
        )
        if delegation_id:
            self.fields['responsables'].queryset = Usuario.objects.filter(
                Q(delegacion_id=delegation_id)
                | Q(delegaciones_autorizadas__pk=delegation_id),
                is_active=True,
            ).distinct().order_by('email')
        else:
            self.fields['responsables'].queryset = Usuario.objects.none()
        self.fields['responsables'].help_text = 'Selecciona al menos un responsable.'


class CompromisoEstadoForm(BootstrapFormMixin, forms.Form):
    estado = forms.ChoiceField(choices=Compromiso.Estado.choices, label='Actualizar estado')