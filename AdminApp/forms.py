from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from FuncionarioApp.models import Subtipo, Tipo
from AdminApp.models import (Cargo,Delegacion,ParametroSistema,PasswordResetAuditEvent,Rol,Usuario,UsuarioCargo,UsuarioDelegacion,UsuarioRol,PROTECTED_ROLE_NAMES)
from AdminApp.roles import (assignable_role_ids,ensure_role_group,is_system_administrator,permission_codenames_for,role_group_name)
from config.forms import BootstrapFormMixin
from config.permissions import PERMISSION_CATALOG, PERMISSION_DESCRIPTIONS
from datetime import timedelta
from CoordinadorApp.models import CargoFuncion, CargoItem, Desempeno, Funcion, Item, Periodo

class PermissionCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def __init__(self, *args, permission_metadata=None, **kwargs):
        self.permission_metadata = permission_metadata or {}
        super().__init__(*args, **kwargs)

    def create_option(self,name,value,label,selected,index,subindex=None,attrs=None,):
        option = super().create_option(name,value,label,selected,index,subindex=subindex,attrs=attrs)
        metadata = self.permission_metadata.get(str(value), {})
        option['permission_module'] = metadata.get('module', '')
        option['permission_description'] = metadata.get('description', '')
        return option


def _configure_user_form_fields(form, actor):
    instance = form.instance
    delegations = Delegacion.objects.filter(
        Q(estado=Delegacion.Estado.ACTIVADO)
        | Q(estado__iexact='activo')
    )
    if instance.pk:
        delegations = Delegacion.objects.filter(
            Q(estado=Delegacion.Estado.ACTIVADO)
            | Q(estado__iexact='activo')
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
    rut = forms.CharField(
        max_length=12,
        required=True,
        label='RUT',
        help_text='Formato sin puntos y con guión (ej: 12345678-9).',
        widget=forms.TextInput(attrs={'placeholder': '12345678-9'}),
    )
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

    class Meta:
        model = Usuario
        fields = ('rut', 'email', 'nombre')
        labels = {
            'rut': 'RUT',
            'email': 'Correo electrónico',
            'nombre': 'Nombre de usuario',
        }

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['nombre'].required = True
        _configure_user_form_fields(self, actor)

    def clean_rut(self):
        from AdminApp.models import validar_y_normalizar_rut_usuario
        rut = validar_y_normalizar_rut_usuario(self.cleaned_data.get('rut'))
        if Usuario.objects.filter(rut__iexact=rut).exists():
            raise forms.ValidationError('Ya existe una cuenta registrada con este RUT.')
        return rut

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe una cuenta registrada con este correo electrónico.')
        return email

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre de usuario es obligatorio.')
        if Usuario.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError('Ya existe una cuenta registrada con este nombre de usuario.')
        return nombre

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
        return cleaned_data

    def save(self, commit=True):
        import secrets
        user = super().save(commit=False)
        user.estado = Usuario.EstadoCuenta.PENDIENTE_ACTIVACION
        user.is_active = True
        user.requiere_cambio_password = True
        user.fecha_activacion = None
        temp_password = f'Sgr#{secrets.token_urlsafe(9)}9'
        user.set_password(temp_password)
        user._generated_temp_password = temp_password
        if commit:
            user.save()
            _sync_user_assignments(user, self.cleaned_data)
        return user


class UsuarioUpdateForm(BootstrapFormMixin, forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        required=False,
        label='RUT',
        widget=forms.TextInput(attrs={'placeholder': '12345678-9'}),
    )
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
    password1 = forms.CharField(label='Nueva contraseña (opcional)', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput, required=False)

    class Meta:
        model = Usuario
        fields = ('rut', 'email', 'nombre', 'estado', 'is_active')
        labels = {
            'rut': 'RUT',
            'email': 'Correo electrónico',
            'nombre': 'Nombre de usuario',
            'estado': 'Estado',
            'is_active': 'Cuenta activa',
        }

    def __init__(self, *args, protected_admin=False, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['nombre'].required = True
        _configure_user_form_fields(self, actor)
        if protected_admin:
            self.fields['cargo'].disabled = True
            self.fields['is_active'].disabled = True

    def clean_rut(self):
        from AdminApp.models import validar_y_normalizar_rut_usuario
        raw = (self.cleaned_data.get('rut') or '').strip()
        if not raw:
            return None
        rut = validar_y_normalizar_rut_usuario(raw)
        qs = Usuario.objects.filter(rut__iexact=rut)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe otra cuenta registrada con este RUT.')
        return rut

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        qs = Usuario.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe otra cuenta registrada con este correo electrónico.')
        return email

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre de usuario es obligatorio.')
        qs = Usuario.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe otra cuenta registrada con este nombre de usuario.')
        return nombre

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
    umbral_rojo = forms.DecimalField(
        label='Umbral mÃ­nimo rojo (%)', min_value=Decimal('0'),
        max_value=Decimal('100'), decimal_places=2, max_digits=6,
        required=False,
    )
    umbral_ambar = forms.DecimalField(
        label='Umbral mÃ­nimo Ã¡mbar (%)', min_value=Decimal('0'),
        max_value=Decimal('100'), decimal_places=2, max_digits=6,
        required=False,
    )
    vigente_desde = forms.DateField(
        label='Vigente desde', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Los cambios se aplican a perÃ­odos abiertos; los cerrados conservan su snapshot.',
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
        initial.setdefault('umbral_rojo', ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_ROJO))
        initial.setdefault('umbral_ambar', ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_AMBAR))
        initial.setdefault('vigente_desde', timezone.localdate())
        super().__init__(*args, initial=initial, **kwargs)

    def clean_max_dias_autorizacion(self):
        return self.cleaned_data.get('max_dias_autorizacion') or ParametroSistema.obtener(
            ParametroSistema.Clave.MAX_DIAS_AUTORIZACION,
        )

    def clean(self):
        cleaned_data = super().clean()
        rojo = cleaned_data.get('umbral_rojo')
        ambar = cleaned_data.get('umbral_ambar')
        if rojo is None:
            rojo = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_ROJO)
            cleaned_data['umbral_rojo'] = rojo
        if ambar is None:
            ambar = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_AMBAR)
            cleaned_data['umbral_ambar'] = ambar
        if rojo is not None and ambar is not None and rojo >= ambar:
            self.add_error('umbral_rojo', 'El umbral rojo debe ser menor que el umbral ámbar.')
        if not cleaned_data.get('vigente_desde'):
            cleaned_data['vigente_desde'] = timezone.localdate()
        vigencia = cleaned_data.get('vigente_desde')
        if vigencia and Periodo.objects.filter(
            estado=Periodo.Estado.CERRADO,
            fecha_inicio__lte=vigencia,
            fecha_fin__gte=vigencia,
        ).exists():
            self.add_error(
                'vigente_desde',
                'La vigencia no puede comenzar dentro de un período cerrado.',
            )
        return cleaned_data


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

def _validate_vigencia_not_in_closed_period(form, vigencia, field_name='vigente_desde'):
    if not vigencia:
        return
    closed_period = Periodo.objects.filter(
        estado=Periodo.Estado.CERRADO,
        fecha_inicio__lte=vigencia,
        fecha_fin__gte=vigencia,
    ).first()
    if closed_period:
        form.add_error(
            field_name,
            f'No se puede fijar vigencia en "{closed_period.nombre}" porque es un período cerrado.',
        )

class CargoForm(BootstrapFormMixin, forms.ModelForm):
    funciones = forms.ModelMultipleChoiceField(
        queryset=Funcion.objects.none(),
        required=False,
        label='Funciones vigentes asociadas',
    )
    items = forms.ModelMultipleChoiceField(
        queryset=Item.objects.none(),
        required=False,
        label='Ítems de medición vigentes',
    )
    vigente_desde = forms.DateField(
        required=True,
        label='Vigente desde',
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Fecha desde la cual rigen los cambios sin alterar períodos cerrados.',
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
        self.fields['funciones'].queryset = Funcion.objects.filter(
            estado=Funcion.Estado.ACTIVO,
        ).order_by('nombre')
        self.fields['items'].queryset = Item.objects.filter(
            estado=Item.Estado.ACTIVO,
        ).order_by('nombre')

        if self.instance.pk:
            hoy = timezone.localdate()
            vigentes_fn = CargoFuncion.objects.filter(
                cargo=self.instance,
            ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=hoy))
            self.initial['funciones'] = list(vigentes_fn.values_list('funcion_id', flat=True))

            vigentes_it = CargoItem.objects.filter(
                cargo=self.instance,
            ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=hoy))
            self.initial['items'] = list(vigentes_it.values_list('item_id', flat=True))

            ultima_fecha = (
                vigentes_fn.order_by('-vigente_desde').values_list('vigente_desde', flat=True).first()
                or vigentes_it.order_by('-vigente_desde').values_list('vigente_desde', flat=True).first()
            )
            if ultima_fecha:
                self.initial['vigente_desde'] = max(ultima_fecha, hoy)

    def clean(self):
        cleaned_data = super().clean()
        vigencia = cleaned_data.get('vigente_desde')
        _validate_vigencia_not_in_closed_period(self, vigencia, 'vigente_desde')
        if vigencia:
            cierre = vigencia - timedelta(days=1)
            _validate_vigencia_not_in_closed_period(self, cierre, 'vigente_desde')
        return cleaned_data

    def save(self, commit=True):
        cargo = super().save(commit=commit)
        if commit:
            with transaction.atomic():
                vigencia = self.cleaned_data.get('vigente_desde') or timezone.localdate()
                fecha_cierre = vigencia - timedelta(days=1)

                # 1. Sincronizar funciones vigentes sin borrar historial cerrado
                selected_fn = {f.pk for f in self.cleaned_data.get('funciones', ())}
                activas_fn = CargoFuncion.objects.filter(
                    cargo=cargo,
                    vigente_hasta__isnull=True,
                )
                for asig in activas_fn.exclude(funcion_id__in=selected_fn):
                    if asig.vigente_desde >= vigencia:
                        asig.delete()
                    else:
                        asig.vigente_hasta = fecha_cierre
                        asig.save(update_fields=['vigente_hasta'])

                current_fn = set(
                    CargoFuncion.objects.filter(
                        cargo=cargo,
                        vigente_hasta__isnull=True,
                    ).values_list('funcion_id', flat=True)
                )
                CargoFuncion.objects.bulk_create([
                    CargoFuncion(cargo=cargo, funcion_id=fn_id, vigente_desde=vigencia)
                    for fn_id in selected_fn - current_fn
                ])

                # 2. Sincronizar ítems medibles vigentes sin borrar historial cerrado
                selected_it = {i.pk for i in self.cleaned_data.get('items', ())}
                activas_it = CargoItem.objects.filter(
                    cargo=cargo,
                    vigente_hasta__isnull=True,
                )
                for asig in activas_it.exclude(item_id__in=selected_it):
                    if asig.vigente_desde >= vigencia:
                        asig.delete()
                    else:
                        asig.vigente_hasta = fecha_cierre
                        asig.save(update_fields=['vigente_hasta'])

                current_it = set(
                    CargoItem.objects.filter(
                        cargo=cargo,
                        vigente_hasta__isnull=True,
                    ).values_list('item_id', flat=True)
                )
                CargoItem.objects.bulk_create([
                    CargoItem(cargo=cargo, item_id=it_id, vigente_desde=vigencia)
                    for it_id in selected_it - current_it
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
        fields = ('cargo', 'funcion', 'vigente_desde', 'vigente_hasta')
        labels = {
            'cargo': 'Cargo',
            'funcion': 'Función',
            'vigente_desde': 'Vigente desde',
            'vigente_hasta': 'Vigente hasta (opcional)',
        }
        widgets = {
            'vigente_desde': forms.DateInput(attrs={'type': 'date'}),
            'vigente_hasta': forms.DateInput(attrs={'type': 'date'}),
        }

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

    def clean(self):
        cleaned_data = super().clean()
        desde = cleaned_data.get('vigente_desde')
        hasta = cleaned_data.get('vigente_hasta')
        if self.instance.pk and self.instance.vigente_desde != desde:
            _validate_vigencia_not_in_closed_period(self, self.instance.vigente_desde, 'vigente_desde')
        _validate_vigencia_not_in_closed_period(self, desde, 'vigente_desde')
        if hasta:
            _validate_vigencia_not_in_closed_period(self, hasta, 'vigente_hasta')
        return cleaned_data


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
        fields = ('codigo', 'nombre', 'descripcion', 'estado')
        labels = {
            'codigo': 'Código',
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'estado': 'Estado',
        }
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


#Esta clase no se utiliza actualmente, pero se deja comentada por si se requiere en el futuro para la gestión de tipos de atención
""" class TipoAtencionForm(BootstrapFormMixin, forms.ModelForm):
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
"""

class TipoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tipo
        fields = ('nombre', 'estado')
        labels = {'nombre': 'Tipo', 'estado': 'Estado'}

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        qs = Tipo.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un tipo con este nombre.')
        return nombre


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
        if self.instance.pk and self.instance.tipo_id:
            tipos = tipos | Tipo.objects.filter(pk=self.instance.tipo_id)
        self.fields['tipo'].queryset = tipos.distinct().order_by('nombre')

    def clean_nombre(self):
        return (self.cleaned_data.get('nombre') or '').strip()

    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get('nombre')
        tipo = cleaned_data.get('tipo') or (self.instance.tipo if self.instance.tipo_id else None)
        if nombre and tipo:
            qs = Subtipo.objects.filter(nombre__iexact=nombre, tipo=tipo)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('nombre', 'Ya existe un subtipo con este nombre para el tipo seleccionado.')
        return cleaned_data

#cambio de formulario para desempeño, agregando validación de ponderación y meta
class DesempenoForm(BootstrapFormMixin, forms.ModelForm):
    meta = forms.DecimalField(
        label='Meta (Cantidad objetivo)',
        min_value=Decimal('0.01'),
        max_digits=12,
        decimal_places=2,
    )
    ponderacion = forms.DecimalField(
        label='Ponderación (%)',
        min_value=Decimal('0.01'),
        max_value=Decimal('100.00'),
        max_digits=5,
        decimal_places=2,
        help_text='Porcentaje de peso de este ítem para el funcionario en el período (la suma debe ser 100%).',
    )

    class Meta:
        model = Desempeno
        fields = ('usuario', 'item', 'periodo', 'meta', 'ponderacion')
        labels = {
            'usuario': 'Funcionario',
            'item': 'Ítem de medición',
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

        items = Item.objects.filter(estado__iexact=Item.Estado.ACTIVO)
        if self.instance.pk and self.instance.item_id:
            items = (items | Item.objects.filter(pk=self.instance.item_id)).distinct()
        self.fields['item'].queryset = items.order_by('nombre')

        periods = (
            Periodo.objects.all()
            if allow_closed_periods
            else Periodo.objects.filter(estado__iexact=Periodo.Estado.ABIERTO)
        )
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
        ponderacion = cleaned_data.get('ponderacion')

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

            if ponderacion is not None:
                from django.db.models import Sum
                otras = Desempeno.objects.filter(usuario=user, periodo=period)
                if self.instance.pk:
                    otras = otras.exclude(pk=self.instance.pk)
                suma_actual = otras.aggregate(total=Sum('ponderacion'))['total'] or Decimal('0')
                if suma_actual + ponderacion > Decimal('100.00'):
                    disponible = Decimal('100.00') - suma_actual
                    self.add_error(
                        'ponderacion',
                        f'La suma de ponderaciones superaría el 100% (disponible: {disponible:.2f}%).',
                    )
        return cleaned_data

    def save(self, commit=True):
        return super().save(commit=commit)

class HistorialFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label='Buscar', required=False, max_length=120)
    entidad = forms.CharField(label='Entidad', required=False, max_length=120)
    usuario = forms.ModelChoiceField(
        label='Usuario',
        required=False,
        queryset=Usuario.objects.filter(is_active=True).order_by('email'),
        empty_label='Todos',
    )
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
