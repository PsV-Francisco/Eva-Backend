from django import forms
from AdminApp.models import Usuario
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import Subtipo, Tipo
from FuncionarioApp.forms import (
    TipoSubtipoFields,
    _assign_tipo_subtipo,
    _set_tipo_subtipo_choices,
)
from config.forms import BootstrapFormMixin


class CompromisoForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.none(),
        required=False,
        label='Tipo',
        empty_label='Sin tipo (predeterminado)',
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=False,
        label='Subtipo',
        empty_label='Sin subtipo (predeterminado)',
    )
    periodo = forms.ModelChoiceField(
        queryset=Periodo.objects.filter(estado=Periodo.Estado.ABIERTO),
        label='Período de agenda',
    )

    class Meta:
        model = Compromiso
        fields = ('periodo', 'descripcion', 'solicitante', 'territorio', 'fecha', 'responsable', 'estado', 'observaciones')
        labels = {
            'descripcion': 'Compromiso',
            'solicitante': 'Solicitante',
            'territorio': 'Territorio',
            'fecha': 'Fecha comprometida',
            'responsable': 'responsable',
            'estado': 'Estado',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
            'responsable': forms.SelectMultiple(attrs={'size': 4}),
        }

    def __init__(self, *args, user, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        _set_tipo_subtipo_choices(self, self.instance)
        delegation_id = (
            delegation.pk if delegation else user.delegacion_id
        )
        if delegation_id:
            self.fields['responsable'].queryset = Usuario.objects.filter(
                usuariodelegacion__delegacion_id=delegation_id,
                usuariodelegacion__fecha_fin__isnull=True,
                is_active=True,
            ).distinct().order_by('email')
        else:
            self.fields['responsable'].queryset = Usuario.objects.none()
        self.fields['responsable'].help_text = 'Selecciona al menos un responsable.'

    def save(self, commit=True):
        instance = super().save(commit=False)
        _assign_tipo_subtipo(self, instance)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class CompromisoEstadoForm(BootstrapFormMixin, forms.Form):
    estado = forms.ChoiceField(choices=Compromiso.Estado.choices, label='Actualizar estado')