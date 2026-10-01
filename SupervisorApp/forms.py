from django import forms

from SupervisorApp.models import RevisionEvidencia
from config.forms import BootstrapFormMixin


class RevisionEvidenciaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RevisionEvidencia
        fields = ('decision', 'observaciones')
        labels = {'decision': 'Decisión', 'observaciones': 'Observación para el funcionario'}
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2})}

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get('decision')
        observation = cleaned_data.get('observaciones', '').strip()
        if decision in ('rechazada', 'correccion') and not observation:
            self.add_error('observaciones', 'Indica el motivo o el ajuste solicitado.')
        return cleaned_data