from django import forms
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from django.db.models import Q

from AdminApp.models import (
    Delegacion,
    ParametroSistema,
    Rol,
    SubAtencion,
    TipoAtencion,
    Usuario,
)
from CoordinadorApp.models import Desempeno, Item, Periodo
from config.forms import BootstrapFormMixin


class UsuarioCreationForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = (
            'email', 'first_name', 'last_name', 'delegacion',
            'delegaciones_autorizadas', 'cargo', 'roles', 'is_active',
        )
        labels = {
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'delegacion': 'Delegación',
            'delegaciones_autorizadas': 'Delegaciones autorizadas',
            'cargo': 'Cargo',
            'roles': 'Roles',
            'is_active': 'Cuenta activa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        delegations = Delegacion.objects.filter(
            estado=Delegacion.Estado.ACTIVA,
        )
        if self.instance.pk:
            delegations = Delegacion.objects.filter(
                Q(estado=Delegacion.Estado.ACTIVA)
                | Q(usuarios=self.instance)
                | Q(usuarios_autorizados=self.instance)
            ).distinct()
        delegations = delegations.order_by('nombre')
        self.fields['delegacion'].queryset = delegations
        self.fields['delegaciones_autorizadas'].queryset = delegations
        roles = Rol.objects.filter(estado=Rol.Estado.ACTIVO)
        if self.instance.pk:
            roles = Rol.objects.filter(
                Q(estado=Rol.Estado.ACTIVO) | Q(usuarios=self.instance),
            ).distinct()
        self.fields['roles'].queryset = roles.order_by('nombre')

    def clean(self):
        cleaned_data = super().clean()
        delegation = cleaned_data.get('delegacion')
        authorized = cleaned_data.get('delegaciones_autorizadas')
        if delegation and authorized is not None:
            if not any(item.pk == delegation.pk for item in authorized):
                cleaned_data['delegaciones_autorizadas'] = [
                    *authorized,
                    delegation,
                ]
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


class DelegacionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Delegacion
        fields = ('codigo', 'nombre', 'direccion', 'comuna', 'estado')
        labels = {
            'codigo': 'Código',
            'nombre': 'Nombre',
            'direccion': 'Dirección',
            'comuna': 'Comuna',
            'estado': 'Estado',
        }


class RolForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Rol
        fields = ('nombre', 'descripcion', 'permisos', 'alcance', 'estado')
        labels = {
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'permisos': 'Permisos',
            'alcance': 'Alcance',
            'estado': 'Estado',
        }
        help_texts = {
            'permisos': (
                'Campo descriptivo del rol. El acceso a los módulos sigue '
                'validándose según el cargo de la cuenta.'
            ),
        }
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'permisos': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe los permisos del rol',
            }),
        }


class ItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ('codigo', 'funcion', 'nombre', 'descripcion', 'estado')
        labels = {
            'codigo': 'Código',
            'funcion': 'Función',
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class TipoAtencionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TipoAtencion
        fields = ('codigo', 'nombre', 'descripcion', 'estado')
        labels = {
            'codigo': 'Código',
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class SubAtencionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SubAtencion
        fields = (
            'codigo', 'nombre', 'tipo_atencion', 'descripcion', 'estado',
        )
        labels = {
            'codigo': 'Código',
            'nombre': 'Nombre',
            'tipo_atencion': 'Tipo de Atención',
            'descripcion': 'Descripción',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_atencion'].queryset = TipoAtencion.objects.order_by(
            'nombre',
        )


class DesempenoForm(BootstrapFormMixin, forms.ModelForm):
    meta = forms.DecimalField(
        label='Meta',
        min_value=Decimal('0.01'),
        max_digits=12,
        decimal_places=2,
    )
    ponderacion = forms.DecimalField(
        label='Ponderación (%)',
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        max_digits=5,
        decimal_places=2,
    )

    class Meta:
        model = Desempeno
        fields = ('usuario', 'item', 'periodo', 'meta', 'ponderacion')
        labels = {
            'usuario': 'Usuario',
            'item': 'Ítem',
            'periodo': 'Período',
        }

    def __init__(self, *args, user=None, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_item_id = self.instance.item_id if self.instance.pk else None
        self._original_function_id = (
            self.instance.funcion_id if self.instance.pk else None
        )
        usuarios = Usuario.objects.filter(is_active=True)
        if user and user.cargo and user.cargo.nombre.strip().casefold() not in {
            'admin', 'administrador',
        }:
            if delegation:
                usuarios = usuarios.filter(
                    Q(delegacion=delegation)
                    | Q(delegaciones_autorizadas=delegation)
                ).distinct()
            else:
                usuarios = usuarios.none()
        if self.instance.pk and self.instance.usuario_id:
            usuarios = (usuarios | Usuario.objects.filter(
                pk=self.instance.usuario_id,
            )).distinct()
        self.fields['usuario'].queryset = usuarios.order_by(
            'last_name', 'first_name', 'email',
        )

        items = Item.objects.filter(estado=Item.Estado.ACTIVO)
        if self.instance.pk and self.instance.item_id:
            items = (items | Item.objects.filter(pk=self.instance.item_id)).distinct()
        self.fields['item'].queryset = items.order_by('nombre')
        periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO)
        if self.instance.pk and self.instance.periodo_id:
            periods = (periods | Periodo.objects.filter(
                pk=self.instance.periodo_id,
            )).distinct()
        self.fields['periodo'].queryset = periods.order_by('-fecha_inicio')

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('usuario')
        item = cleaned_data.get('item')
        period = cleaned_data.get('periodo')
        if user and item and period:
            function_id = (
                self._original_function_id
                if self.instance.pk and item.pk == self._original_item_id
                else item.funcion_id
            )
            duplicate = Desempeno.objects.filter(
                usuario=user,
                item=item,
                periodo=period,
                funcion_id=function_id,
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error(
                    'item',
                    'Ya existe una meta para este usuario, ítem y período.',
                )
        return cleaned_data

    def save(self, commit=True):
        record = super().save(commit=False)
        if not self.instance.pk or record.item_id != self._original_item_id:
            record.funcion = record.item.funcion
        else:
            record.funcion_id = self._original_function_id
        if commit:
            record.save()
            self.save_m2m()
        return record