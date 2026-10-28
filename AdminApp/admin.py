from django.contrib import admin
from django import forms
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import (
	Cargo,
	Catalogo,
	Delegacion,
	Historial,
	ParametroSistema,
	PasswordResetAuditEvent,
	Rol,
	SubAtencion,
	TipoAtencion,
	Usuario,
)
from .audit import registrar_historial


try:
	admin.site.unregister(Group)
except NotRegistered:
	pass


class UsuarioCreationForm(forms.ModelForm):
	password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
	password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

	class Meta:
		model = Usuario
		fields = ('email',)

	def clean_password2(self):
		password1 = self.cleaned_data.get('password1')
		password2 = self.cleaned_data.get('password2')
		if password1 and password2 and password1 != password2:
			raise forms.ValidationError('Las contraseñas no coinciden.')
		return password2

	def save(self, commit=True):
		user = super().save(commit=False)
		user.set_password(self.cleaned_data['password1'])
		if commit:
			user.save()
		return user


class UsuarioChangeForm(forms.ModelForm):
	password = ReadOnlyPasswordHashField(
		label='Contraseña',
		help_text='La contraseña se almacena cifrada y no se puede consultar.',
	)

	class Meta:
		model = Usuario
		fields = '__all__'

	def clean_password(self):
		return self.initial.get('password')


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
	form = UsuarioChangeForm
	add_form = UsuarioCreationForm
	add_fieldsets = (
		(None, {'classes': ('wide',), 'fields': ('email', 'password1', 'password2')}),
	)
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Información personal', {'fields': ('first_name', 'last_name', 'delegacion', 'cargo', 'roles')}),
		('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
		('Fechas', {'fields': ('last_login', 'date_joined')}),
	)
	list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
	list_filter = ('is_staff', 'is_superuser', 'is_active', 'delegacion', 'cargo')
	search_fields = ('email', 'first_name', 'last_name')
	ordering = ('email',)
	filter_horizontal = ('roles',)

	def save_model(self, request, obj, form, change):
		obj._roles_before_save = (
			set(obj.roles.values_list('pk', flat=True))
			if change else set()
		)
		super().save_model(request, obj, form, change)

	def save_related(self, request, form, formsets, change):
		super().save_related(request, form, formsets, change)
		roles_after = set(
			form.instance.roles.values_list('pk', flat=True),
		)
		roles_before = form.instance._roles_before_save
		if roles_before != roles_after:
			registrar_historial(
				actor=request.user,
				action='Cambiar asignación de roles',
				entity=f'Usuario:{form.instance.pk}',
				before={'roles': sorted(roles_before)},
				after={'roles': sorted(roles_after)},
			)

	def has_module_permission(self, request):
		return request.user.is_superuser

	def has_view_permission(self, request, obj=None):
		return request.user.is_superuser

	def has_add_permission(self, request):
		return request.user.is_superuser

	def has_change_permission(self, request, obj=None):
		return request.user.is_superuser

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre', 'comuna', 'estado')
	list_filter = ('estado',)
	search_fields = ('codigo', 'nombre', 'direccion', 'comuna')


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'funciones')
	search_fields = ('nombre', 'funciones__nombre')


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'alcance', 'estado')
	list_filter = ('alcance', 'estado')
	search_fields = ('nombre', 'descripcion', 'permisos')

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(TipoAtencion)
class TipoAtencionAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre', 'estado')
	list_filter = ('estado',)
	search_fields = ('codigo', 'nombre', 'descripcion')


@admin.register(SubAtencion)
class SubAtencionAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre', 'tipo_atencion', 'estado')
	list_filter = ('tipo_atencion', 'estado')
	search_fields = ('codigo', 'nombre', 'tipo_atencion__nombre', 'descripcion')


@admin.register(Catalogo)
class CatalogoAdmin(admin.ModelAdmin):
	list_display = ('actividad', 'servicio', 'tipo', 'subtipo')
	list_filter = ('tipo', 'subtipo')
	search_fields = ('actividad', 'servicio', 'tipo', 'subtipo')


@admin.register(Historial)
class HistorialAdmin(admin.ModelAdmin):
	list_display = ('accion', 'autor', 'periodo', 'fecha_modificacion')
	list_filter = ('accion', 'periodo', 'fecha_modificacion')
	search_fields = ('accion', 'autor__email', 'object_id')
	readonly_fields = ('fecha_modificacion', 'valor_anterior', 'valor_nuevo')


@admin.register(ParametroSistema)
class ParametroSistemaAdmin(admin.ModelAdmin):
	list_display = ('clave', 'valor')
	readonly_fields = ('clave',)


@admin.register(PasswordResetAuditEvent)
class PasswordResetAuditEventAdmin(admin.ModelAdmin):
	list_display = ('action', 'user', 'ip_address', 'was_rate_limited', 'created_at')
	list_filter = ('action', 'was_rate_limited', 'created_at')
	search_fields = ('user__email', 'email_fingerprint', 'ip_address')
	readonly_fields = (
		'user',
		'action',
		'email_fingerprint',
		'ip_address',
		'was_rate_limited',
		'created_at',
	)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False
