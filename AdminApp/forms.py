from django import forms
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal

from AdminApp.models import ParametroSistema, Usuario
from config.forms import BootstrapFormMixin


class UsuarioCreationForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ('email', 'first_name', 'last_name', 'delegacion', 'cargo', 'roles', 'is_active')
        labels = {
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'delegacion': 'Delegación',
            'cargo': 'Cargo',
            'roles': 'Roles',
            'is_active': 'Cuenta activa',
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password1')
        password_confirmation = cleaned_data.get('password2')
        if password and password_confirmation and password != password_confirmation:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif password:
            validate_password(password)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UsuarioUpdateForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Nueva contraseña', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput, required=False)

    class Meta(UsuarioCreationForm.Meta):
        pass

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password1')
        password_confirmation = cleaned_data.get('password2')
        if password != password_confirmation:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif password:
            validate_password(password, self.instance)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class ParametroSistemaForm(BootstrapFormMixin, forms.Form):
    tope_cumplimiento = forms.DecimalField(
        label='Tope de cumplimiento (%)',
        min_value=Decimal('100'),
        max_value=Decimal('999.99'),
        decimal_places=2,
        max_digits=6,
    )
    umbral_delegacion = forms.DecimalField(
        label='Umbral mínimo de delegación (%)',
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        decimal_places=2,
        max_digits=6,
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.pop('initial', {})
        initial.setdefault(
            'tope_cumplimiento',
            ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO),
        )
        initial.setdefault(
            'umbral_delegacion',
            ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION),
        )
        super().__init__(*args, initial=initial, **kwargs)