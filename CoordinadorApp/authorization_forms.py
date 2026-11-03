from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from CoordinadorApp.models import Periodo, SolicitudAutorizacionPeriodo
from CoordinadorApp.services import validate_authorization_expiry
from config.forms import BootstrapFormMixin


class AuthorizationRequestForm(BootstrapFormMixin, forms.ModelForm):
    funcionarios = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=True,
        label='Funcionarios autorizados',
        help_text='Solo sus metas podrán modificarse con esta autorización.',
    )

    class Meta:
        model = SolicitudAutorizacionPeriodo
        fields = ('periodo', 'funcionarios', 'motivo')
        labels = {'periodo': 'Período cerrado', 'motivo': 'Motivo'}
        widgets = {'motivo': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['periodo'].queryset = Periodo.objects.filter(
            estado=Periodo.Estado.CERRADO,
        )
        self.fields['funcionarios'].queryset = get_user_model().objects.filter(
            is_active=True,
        ).order_by('last_name', 'first_name', 'email')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('periodo') and cleaned['periodo'].estado != Periodo.Estado.CERRADO:
            self.add_error('periodo', 'La solicitud solo aplica a períodos cerrados.')
        return cleaned


class AuthorizationDecisionForm(BootstrapFormMixin, forms.Form):
    vence_en = forms.DateTimeField(
        label='Vigente hasta',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False,
    )
    comentario = forms.CharField(
        label='Comentario', widget=forms.Textarea(attrs={'rows': 3}),
    )

    def clean_vence_en(self):
        value = self.cleaned_data.get('vence_en')
        error = validate_authorization_expiry(value)
        if error:
            raise ValidationError(error)
        return value


class AuthorizationRevokeForm(BootstrapFormMixin, forms.Form):
    comentario = forms.CharField(
        label='Motivo de revocación', widget=forms.Textarea(attrs={'rows': 3}),
    )
