from django import forms
from django.contrib.auth.password_validation import validate_password

from AdminApp.models import Usuario
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