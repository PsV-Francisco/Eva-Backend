from django.contrib import admin
from django import forms
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.models import Group
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from AdminApp.models import Cargo,Delegacion,Alerta,Comentarios,Historial,ParametroSistema,PasswordResetAuditEvent,Rol,Usuario
from FuncionarioApp.models import Tipo,Subtipo

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
class UsuarioAdmin(admin.ModelAdmin):
	form = UsuarioChangeForm
	add_form = UsuarioCreationForm
	list_display = ('email', 'nombre', 'estado', 'is_staff', 'is_active')
	list_filter = ('estado', 'is_staff', 'is_superuser', 'is_active')
	search_fields = ('email', 'nombre', 'first_name', 'last_name')
	ordering = ('email',)

	def get_fieldsets(self, request, obj=None):
		if obj is None:
			return ((None, {'fields': ('email', 'password1', 'password2')}),)
		return (
			(None, {'fields': ('email', 'password')}),
			('Información personal', {'fields': ('nombre', 'first_name', 'last_name', 'estado')}),
			('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
			('Fechas', {'fields': ('last_login', 'date_joined')}),
		)

	def get_form(self, request, obj=None, **kwargs):
		kwargs['form'] = self.add_form if obj is None else self.form
		return super().get_form(request, obj, **kwargs)

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
	list_display = ('nombre', 'direccion', 'estado')
	list_filter = ('estado',)
	search_fields = ('nombre', 'direccion')


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'estado', 'function_names')
	list_filter = ('estado',)
	search_fields = ('nombre', 'asignaciones_funciones__funcion__nombre')

	@admin.display(description='Funciones')
	def function_names(self, obj):
		return ', '.join(
			obj.asignaciones_funciones.select_related('funcion').values_list(
				'funcion__nombre', flat=True,
			)
		)


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'estado', 'permisos')
	list_filter = ('estado',)
	search_fields = ('nombre', 'permisos')

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(Tipo)
class TipoAtencionAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'estado')
	list_filter = ('estado',)
	search_fields = ('nombre',)


@admin.register(Subtipo)
class SubAtencionAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'tipo', 'estado')
	list_filter = ('tipo', 'estado')
	search_fields = ('nombre', 'tipo__nombre')


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


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
	list_display = ('motivo', 'fecha', 'estado', 'destinatario')
	list_filter = ('estado', 'fecha')
	search_fields = ('motivo', 'destinatario__email')


@admin.register(Comentarios)
class ComentariosAdmin(admin.ModelAdmin):
	list_display = ('fecha', 'autor', 'registro', 'compromiso')
	list_filter = ('fecha',)
	search_fields = (
		'texto',
		'autor__email',
		'registro__descripcion',
		'compromiso__descripcion',
	)
	readonly_fields = (
		'autor_registro',
		'item_registro',
		'periodo_registro',
		'responsable_compromiso',
		'agenda_compromiso',
		'periodo_agenda_compromiso',
		'agenda_delegacion_compromiso',
	)
