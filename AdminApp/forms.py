from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from FuncionarioApp.models import Subtipo, Tipo
from AdminApp.models import (
    Cargo,
    Delegacion,
    ParametroSistema,
    PasswordResetAuditEvent,
    Rol,
    TipoAtencion,
    Usuario,
    UsuarioCargo,
    UsuarioDelegacion,
    UsuarioRol,
    PROTECTED_ROLE_NAMES,
)
from AdminApp.roles import (
    assignable_role_ids,
    ensure_role_group,
    is_system_administrator,
    permission_codenames_for,
    role_group_name,
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
            | Q(usuariodelegacion__usuario=instance)
        ).distinct()
    form.fields['delegacion'].queryset = delegations.order_by('nombre')
    form.fields['delegaciones_autorizadas'].queryset = (
        delegations.order_by('nombre')
    )
    if instance.pk:
        form.fields['delegacion'].initial = (
            instance.delegacion_actual.delegacion_id
            if instance.delegacion_actual else None
        )
        form.fields['delegaciones_autorizadas'].initial = (
            UsuarioDelegacion.objects.filter(
                usuario=instance,
                fecha_fin__isnull=True,
            ).values_list('delegacion_id', flat=True)
        )

    cargos = Cargo.objects.filter(estado=Cargo.Estado.ACTIVO)
    if instance.pk and instance.cargo_actual:
        cargos = Cargo.objects.filter(
            Q(estado=Cargo.Estado.ACTIVO)
            | Q(pk=instance.cargo_actual.cargo_id),
        )
    form.fields['cargo'].queryset = cargos.order_by('nombre')
    if instance.pk and instance.cargo_actual:
        form.fields['cargo'].initial = instance.cargo_actual.cargo_id

    roles = Rol.objects.filter(estado=Rol.Estado.ACTIVO)
    if instance.pk:
        roles = Rol.objects.filter(
            Q(estado=Rol.Estado.ACTIVO)
            | Q(usuariorol__usuario=instance, usuariorol__fecha_fin__isnull=True),
        ).distinct()
    assignable = assignable_role_ids(actor, instance) if actor else None
    if assignable is not None:
        roles = roles.filter(pk__in=assignable)
    form.fields['roles'].queryset = roles.order_by('nombre')
    if instance.pk:
        form.fields['roles'].initial = UsuarioRol.objects.filter(
            usuario=instance,
            fecha_fin__isnull=True,
        ).values_list('rol_id', flat=True)


def _sync_user_assignments(user, cleaned_data):
    with transaction.atomic():
        now = timezone.now()
        main_delegation = cleaned_data.get('delegacion')
        delegations = cleaned_data.get('delegaciones_autorizadas') or ()
        delegation_ids = {delegation.pk for delegation in delegations}
        if main_delegation:
            delegation_ids.add(main_delegation.pk)
        active_delegations = list(UsuarioDelegacion.objects.select_for_update().filter(
            usuario=user,
            fecha_fin__isnull=True,
        ))
        by_delegation = {}
        for assignment in active_delegations:
            by_delegation.setdefault(assignment.delegacion_id, []).append(assignment)
        for delegation_id, assignments in by_delegation.items():
            if delegation_id not in delegation_ids:
                for assignment in assignments:
                    assignment.fecha_fin = now
                    assignment.save(update_fields=['fecha_fin'])
            else:
                for duplicate in assignments[1:]:
                    duplicate.fecha_fin = now
                    duplicate.save(update_fields=['fecha_fin'])
        for delegation_id in delegation_ids:
            if not by_delegation.get(delegation_id):
                UsuarioDelegacion.objects.create(
                    usuario=user,
                    delegacion_id=delegation_id,
                    fecha_inicio=now,
                )
        if main_delegation:
            UsuarioDelegacion.objects.filter(
                usuario=user,
                delegacion=main_delegation,
                fecha_fin__isnull=True,
            ).update(fecha_inicio=now)

        selected_cargo = cleaned_data.get('cargo')
        cargo_assignments = list(UsuarioCargo.objects.select_for_update().filter(
            usuario=user,
            fecha_fin__isnull=True,
        ))
        keep_cargo = next(
            (assignment for assignment in cargo_assignments
             if selected_cargo and assignment.cargo_id == selected_cargo.pk),
            None,
        )
        for assignment in cargo_assignments:
            if assignment is not keep_cargo:
                assignment.fecha_fin = now
                assignment.save(update_fields=['fecha_fin'])
        if selected_cargo and keep_cargo is None:
            UsuarioCargo.objects.create(
                usuario=user,
                cargo=selected_cargo,
                fecha_inicio=now,
            )

        selected_role_ids = {
            role.pk for role in (cleaned_data.get('roles') or ())
        }
        active_roles = list(UsuarioRol.objects.select_for_update().filter(
            usuario=user,
            fecha_fin__isnull=True,
        ))
        active_role_ids = {assignment.rol_id for assignment in active_roles}
        for assignment in active_roles:
            if assignment.rol_id not in selected_role_ids:
                assignment.fecha_fin = now
                assignment.save(update_fields=['fecha_fin'])
        for role_id in selected_role_ids - active_role_ids:
            UsuarioRol.objects.create(
                usuario=user,
                rol_id=role_id,
                fecha_inicio=now,
            )
        from AdminApp.roles import synchronize_user_role_groups
        synchronize_user_role_groups(user)


class UsuarioCreationForm(BootstrapFormMixin, forms.ModelForm):
    delegacion = forms.ModelChoiceField(
        queryset=Delegacion.objects.none(),
        required=False,
        label='Delegación principal',
    )
    delegaciones_autorizadas = forms.ModelMultipleChoiceField(
        queryset=Delegacion.objects.none(),
        required=False,
        label='Delegaciones autorizadas',
    )
    cargo = forms.ModelChoiceField(
        queryset=Cargo.objects.none(),
        required=True,
        label='Cargo',
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Rol.objects.none(),
        required=False,
        label='Roles',
    )
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ('email', 'nombre', 'estado', 'is_active')
        labels = {
            'email': 'Correo electrónico',
            'nombre': 'Nombre',
            'estado': 'Estado',
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
            _sync_user_assignments(user, self.cleaned_data)
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
            _sync_user_assignments(user, self.cleaned_data)
        return user


class ParametroSistemaForm(BootstrapFormMixin, forms.Form):
    max_dias_autorizacion = forms.IntegerField(
        label='Máximo de días de autorización', min_value=1, max_value=365,
        required=False,
    )
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
        initial.setdefault(
            'max_dias_autorizacion',
            ParametroSistema.obtener(ParametroSistema.Clave.MAX_DIAS_AUTORIZACION),
        )
        super().__init__(*args, initial=initial, **kwargs)

    def clean_max_dias_autorizacion(self):
        return self.cleaned_data.get('max_dias_autorizacion') or ParametroSistema.obtener(
            ParametroSistema.Clave.MAX_DIAS_AUTORIZACION,
        )


class DelegacionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Delegacion
        fields = ('nombre', 'direccion', 'estado')
        labels = {
            'nombre': 'Nombre',
            'direccion': 'Dirección',
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
        fields = ('nombre', 'permisos', 'estado')
        labels = {
            'nombre': 'Nombre',
            'permisos': 'Permisos asignados',
            'estado': 'Estado',
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
        current_group = (
            ensure_role_group(self.instance)
            if self.instance.pk else None
        )
        if self.actor and not is_system_administrator(self.actor):
            existing_codenames = (
                set(
                    current_group.permissions.values_list(
                        'codename',
                        flat=True,
                    )
                )
                if current_group else set()
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
        if current_group:
            self.initial['permissions'] = list(
                current_group.permissions.filter(
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
        if (
            self.instance.pk
            and self.instance.nombre.strip().casefold() in PROTECTED_ROLE_NAMES
        ):
            for field in self.fields.values():
                field.disabled = True

    def clean_permissions(self):
        selected = self.cleaned_data['permissions']
        if not self.actor or is_system_administrator(self.actor):
            return selected
        current = (
            set(
                ensure_role_group(self.instance).permissions.values_list(
                    'codename',
                    flat=True,
                )
            )
            if self.instance.pk else set()
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
            and not (
                self.instance.pk
                and self.instance.nombre.strip().casefold() in PROTECTED_ROLE_NAMES
            )
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
        group.permissions.set(self.cleaned_data['permissions'])
        return role


class CargoForm(BootstrapFormMixin, forms.ModelForm):
    funciones = forms.ModelMultipleChoiceField(
        queryset=Funcion.objects.none(),
        required=False,
        label='Funciones asociadas',
    )

    class Meta:
        model = Cargo
        fields = ('nombre', 'estado')
        labels = {
            'nombre': 'Cargo',
            'estado': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        functions = Funcion.objects.filter(estado=Funcion.Estado.ACTIVO)
        self.fields['funciones'].queryset = functions.order_by('nombre')
        if self.instance.pk:
            self.initial['funciones'] = CargoFuncion.objects.filter(
                cargo=self.instance,
            ).values_list('funcion_id', flat=True)

    def save(self, commit=True):
        cargo = super().save(commit=commit)
        if commit:
            selected = {
                funcion.pk for funcion in self.cleaned_data.get('funciones', ())
            }
            existing = CargoFuncion.objects.filter(cargo=cargo)
            existing.exclude(funcion_id__in=selected).delete()
            current = set(existing.values_list('funcion_id', flat=True))
            CargoFuncion.objects.bulk_create([
                CargoFuncion(cargo=cargo, funcion_id=funcion_id)
                for funcion_id in selected - current
            ])
        return cargo


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


"""class CatalogoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Catalogo
        fields = ('actividad', 'servicio', 'tipo', 'subtipo', 'estado')
        labels = {
            'actividad': 'Actividad',
            'servicio': 'Servicio',
            'tipo': 'Tipo',
            'subtipo': 'Subtipo',
            'estado': 'Estado',
        }"""


class ItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ('codigo', 'nombre', 'descripcion', 'ponderacion', 'estado')
        labels = {
            'codigo': 'Código',
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'ponderacion': 'Ponderación (%)',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class TipoAtencionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TipoAtencion
        fields = ('nombre', 'descripcion', 'subtipo', 'estado')
        labels = {
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'subtipo': 'Subtipo',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class TipoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tipo
        fields = ('nombre', 'estado')
        labels = {'nombre': 'Tipo', 'estado': 'Estado'}


class SubtipoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Subtipo
        fields = ('nombre', 'tipo', 'estado')
        labels = {
            'nombre': 'Subtipo',
            'tipo': 'Tipo',
            'estado': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipos = Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO)
        if self.instance.pk:
            tipos = tipos | Tipo.objects.filter(pk=self.instance.tipo_id)
        self.fields['tipo'].queryset = tipos.distinct().order_by('nombre')


class DesempenoForm(BootstrapFormMixin, forms.ModelForm):
    meta = forms.DecimalField(
        label='Meta',
        min_value=Decimal('0.01'),
        max_digits=12,
        decimal_places=2,
    )
    class Meta:
        model = Desempeno
        fields = ('usuario', 'item', 'periodo', 'meta')
        labels = {
            'usuario': 'Usuario',
            'item': 'Ítem',
            'periodo': 'Período',
        }

    def __init__(
        self, *args, user=None, delegation=None, global_scope=False,
        allow_closed_periods=False, meta_only=False, **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if meta_only:
            for field_name in ('usuario', 'item', 'periodo'):
                self.fields[field_name].disabled = True
        usuarios = Usuario.objects.filter(is_active=True)
        if (
            user and not global_scope and user.cargo
            and user.cargo.nombre.strip().casefold() not in {
            'admin', 'administrador',
            }
        ):
            if delegation:
                usuarios = usuarios.filter(
                    usuariodelegacion__delegacion=delegation,
                    usuariodelegacion__fecha_fin__isnull=True,
                ).distinct()
            else:
                usuarios = usuarios.none()
        if self.instance.pk and self.instance.usuario_id:
            usuarios = (usuarios | Usuario.objects.filter(
                pk=self.instance.usuario_id,
            )).distinct()
        self.fields['usuario'].queryset = usuarios.order_by('nombre', 'email')

        items = Item.objects.filter(
            estado=Item.Estado.ACTIVO,
        )
        if self.instance.pk and self.instance.item_id:
            items = (items | Item.objects.filter(pk=self.instance.item_id)).distinct()
        self.fields['item'].queryset = items.order_by('nombre')
        periods = Periodo.objects.all() if allow_closed_periods else Periodo.objects.filter(estado=Periodo.Estado.ABIERTO)
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
            duplicate = Desempeno.objects.filter(
                usuario=user,
                item=item,
                periodo=period,
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
        return super().save(commit=commit)


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
