from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from django.db.models import Q

from AdminApp.models import (
    Catalogo,
    Cargo,
    Delegacion,
    ParametroSistema,
    PasswordResetAuditEvent,
    Rol,
    SubAtencion,
    TipoAtencion,
    Usuario,
    PROTECTED_ROLE_NAMES,
)
from AdminApp.roles import (
    assignable_role_ids,
    ensure_role_group,
    is_system_administrator,
    permission_codenames_for,
)
from CoordinadorApp.models import CargoFuncion, Desempeno, Funcion, Item, Periodo
from config.forms import BootstrapFormMixin
from config.permissions import PERMISSION_CATALOG, PERMISSION_DESCRIPTIONS


class PermissionCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def __init__(self, *args, permission_metadata=None, **kwargs):
        self.permission_metadata = permission_metadata or {}
        super().__init__(*args, **kwargs)

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        metadata = self.permission_metadata.get(str(value), {})
        option['permission_module'] = metadata.get('module', '')
        option['permission_description'] = metadata.get('description', '')
        return option


def _configure_user_form_fields(form, actor):
    instance = form.instance
    delegations = Delegacion.objects.filter(
        estado=Delegacion.Estado.ACTIVA,
    )
    if instance.pk:
        delegations = Delegacion.objects.filter(
            Q(estado=Delegacion.Estado.ACTIVA)
            | Q(usuarios=instance)
            | Q(usuarios_autorizados=instance)
        ).distinct()
    form.fields['delegacion'].queryset = delegations.order_by('nombre')
    form.fields['delegaciones_autorizadas'].queryset = (
        delegations.order_by('nombre')
    )

    cargos = Cargo.objects.filter(estado=Cargo.Estado.ACTIVO)
    if instance.pk and instance.cargo_id:
        cargos = Cargo.objects.filter(
            Q(estado=Cargo.Estado.ACTIVO) | Q(pk=instance.cargo_id),
        )
    form.fields['cargo'].queryset = cargos.order_by('nombre')

    roles = Rol.objects.filter(estado=Rol.Estado.ACTIVO)
    if instance.pk:
        roles = Rol.objects.filter(
            Q(estado=Rol.Estado.ACTIVO) | Q(usuarios=instance),
        ).distinct()
    assignable = assignable_role_ids(actor, instance) if actor else None
    if assignable is not None:
        roles = roles.filter(pk__in=assignable)
    form.fields['roles'].queryset = roles.order_by('nombre')


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
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        _configure_user_form_fields(self, actor)

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

    def __init__(self, *args, protected_admin=False, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        _configure_user_form_fields(self, actor)
        if protected_admin:
            self.fields['cargo'].disabled = True
            self.fields['is_active'].disabled = True

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
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        label='Permisos',
        widget=PermissionCheckboxSelectMultiple,
    )

    class Meta:
        model = Rol
        fields = ('nombre', 'descripcion', 'alcance', 'estado')
        labels = {
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'alcance': 'Alcance',
            'estado': 'Estado',
        }
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        definitions_by_codename = {
            definition.codename: definition
            for definition in PERMISSION_CATALOG
        }
        permissions = Permission.objects.filter(
            content_type__app_label='AdminApp',
            codename__in=definitions_by_codename,
        ).order_by('name')
        if self.actor and not is_system_administrator(self.actor):
            existing_codenames = (
                set(
                    self.instance.grupo.permissions.values_list(
                        'codename',
                        flat=True,
                    )
                )
                if self.instance.pk and self.instance.grupo_id else set()
            )
            allowed_codenames = (
                permission_codenames_for(self.actor) | existing_codenames
            )
            permissions = permissions.filter(
                codename__in=allowed_codenames,
            )
        self.fields['permissions'].queryset = permissions
        self.fields['permissions'].widget.permission_metadata = {
            str(permission.pk): {
                'module': definitions_by_codename[
                    permission.codename
                ].module,
                'description': PERMISSION_DESCRIPTIONS.get(
                    permission.codename,
                    '',
                ),
            }
            for permission in permissions
        }
        groups = {}
        permission_by_codename = {
            permission.codename: permission
            for permission in permissions
        }
        for definition in PERMISSION_CATALOG:
            permission = permission_by_codename.get(definition.codename)
            if permission:
                groups.setdefault(definition.module, []).append(
                    (permission.pk, definition.label),
                )
        self.fields['permissions'].choices = [
            (module, choices)
            for module, choices in groups.items()
        ]
        if self.instance.pk and self.instance.grupo_id:
            self.initial['permissions'] = list(
                self.instance.grupo.permissions.filter(
                    codename__in=definitions_by_codename,
                ).values_list('pk', flat=True)
            )
        permission_field = self['permissions']
        widget_context = self.fields['permissions'].widget.get_context(
            'permissions',
            permission_field.value(),
            {'id': permission_field.auto_id},
        )['widget']
        self.permission_groups = [
            {
                'module': module,
                'choices': choices,
                'selected_count': sum(
                    option['selected'] for option in choices
                ),
                'total': len(choices),
            }
            for module, choices, _ in widget_context['optgroups']
        ]
        if self.instance.protegido:
            for field in self.fields.values():
                field.disabled = True

    def clean_permissions(self):
        selected = self.cleaned_data['permissions']
        if not self.actor or is_system_administrator(self.actor):
            return selected
        current = (
            set(
                self.instance.grupo.permissions.values_list(
                    'codename',
                    flat=True,
                )
            )
            if self.instance.pk and self.instance.grupo_id else set()
        )
        permitted = permission_codenames_for(self.actor) | current
        unauthorized = {
            permission.codename
            for permission in selected
        } - permitted
        if unauthorized:
            raise forms.ValidationError(
                'No puedes asignar permisos que tu propia cuenta no posee.'
            )
        return selected

    def clean_nombre(self):
        name = self.cleaned_data['nombre'].strip()
        if (
            name.casefold() in PROTECTED_ROLE_NAMES
            and not self.instance.protegido
        ):
            raise forms.ValidationError(
                'Este nombre está reservado para roles críticos del sistema.'
            )
        return name

    def save(self, commit=True):
        role = super().save(commit=False)
        if not commit:
            return role
        role.save()
        group = ensure_role_group(role)
        if not role.protegido:
            group.permissions.set(self.cleaned_data['permissions'])
        return role


class CargoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ('nombre', 'funciones', 'estado')
        labels = {
            'nombre': 'Cargo',
            'funciones': 'Función asociada',
            'estado': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        functions = Funcion.objects.filter(estado=Funcion.Estado.ACTIVO)
        if self.instance.pk and self.instance.funciones_id:
            functions = Funcion.objects.filter(
                Q(estado=Funcion.Estado.ACTIVO)
                | Q(pk=self.instance.funciones_id),
            )
        self.fields['funciones'].queryset = functions.order_by('nombre')


class FuncionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Funcion
        fields = ('nombre', 'descripcion', 'estado')
        labels = {
            'nombre': 'Función',
            'descripcion': 'Descripción',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class CargoFuncionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CargoFuncion
        fields = ('cargo', 'funcion')
        labels = {'cargo': 'Cargo', 'funcion': 'Función'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cargos = Cargo.objects.filter(estado=Cargo.Estado.ACTIVO)
        if self.instance.pk:
            cargos = Cargo.objects.filter(
                Q(estado=Cargo.Estado.ACTIVO)
                | Q(pk=self.instance.cargo_id),
            )
        functions = Funcion.objects.filter(estado=Funcion.Estado.ACTIVO)
        if self.instance.pk:
            functions = Funcion.objects.filter(
                Q(estado=Funcion.Estado.ACTIVO)
                | Q(pk=self.instance.funcion_id),
            )
        self.fields['cargo'].queryset = cargos.order_by('nombre')
        self.fields['funcion'].queryset = functions.order_by('nombre')


class CatalogoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Catalogo
        fields = ('actividad', 'servicio', 'tipo', 'subtipo', 'estado')
        labels = {
            'actividad': 'Actividad',
            'servicio': 'Servicio',
            'tipo': 'Tipo',
            'subtipo': 'Subtipo',
            'estado': 'Estado',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        functions = Funcion.objects.filter(estado=Funcion.Estado.ACTIVO)
        if self.instance.pk and self.instance.funcion_id:
            functions = Funcion.objects.filter(
                Q(estado=Funcion.Estado.ACTIVO)
                | Q(pk=self.instance.funcion_id),
            )
        self.fields['funcion'].queryset = functions.order_by('nombre')


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

        items = Item.objects.filter(
            estado=Item.Estado.ACTIVO,
            funcion__estado=Funcion.Estado.ACTIVO,
        )
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


class HistorialFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label='Buscar', required=False, max_length=120)
    accion = forms.ChoiceField(label='Acción', required=False)
    desde = forms.DateField(
        label='Desde',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    hasta = forms.DateField(
        label='Hasta',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, *args, actions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accion'].choices = [('', 'Todas')] + [
            (action, action) for action in actions
        ]

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('desde')
        end = cleaned_data.get('hasta')
        if start and end and end < start:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
        return cleaned_data


class PasswordResetAuditFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label='Buscar', required=False, max_length=120)
    accion = forms.ChoiceField(
        label='Tipo de evento',
        required=False,
        choices=(('', 'Todos'), *PasswordResetAuditEvent.Action.choices),
    )
    limitada = forms.ChoiceField(
        label='Límite aplicado',
        required=False,
        choices=(('', 'Todos'), ('si', 'Sí'), ('no', 'No')),
    )
    desde = forms.DateField(
        label='Desde',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    hasta = forms.DateField(
        label='Hasta',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('desde')
        end = cleaned_data.get('hasta')
        if start and end and end < start:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
        return cleaned_data