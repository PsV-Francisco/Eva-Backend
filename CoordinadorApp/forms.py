from django import forms

from CoordinadorApp.models import Periodo
from config.forms import BootstrapFormMixin


class PeriodoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Periodo
        fields = ('nombre', 'fecha_inicio', 'fecha_fin', 'estado')
        labels = {
            'nombre': 'Nombre del período',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_fin': 'Fecha de término',
            'estado': 'Estado',
        }
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('fecha_inicio')
        end = cleaned_data.get('fecha_fin')
        if start and end and end < start:
            self.add_error('fecha_fin', 'La fecha de término debe ser igual o posterior al inicio.')
        return cleaned_data