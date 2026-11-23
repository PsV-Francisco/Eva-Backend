from django import forms
from SupervisorApp.models import RevisionEvidencia
from config.forms import BootstrapFormMixin

class RevisionEvidenciaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RevisionEvidencia
        fields = ('decision', 'observaciones')
        labels = {'decision': 'Decisión', 'observaciones': 'Observación para el funcionario'}
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2})}

#Mejora del codigo para que el campo observaciones sea obligatorio cuando la decisión es rechazada o corrección.
    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get('decision')
        observation = cleaned_data.get('observaciones', '').strip()
        if decision in (
            RevisionEvidencia.Decision.RECHAZADA,
            RevisionEvidencia.Decision.CORRECCION,
        ) and not observation:
            self.add_error('observaciones', 'Indica el motivo o los antecedentes solicitados.')
        return cleaned_data