from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import Cargo, Catalogo, Delegacion, Historial, Rol, Usuario


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
		('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Fechas', {'fields': ('last_login', 'date_joined')}),
	)
	list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
	list_filter = ('is_staff', 'is_superuser', 'is_active', 'delegacion', 'cargo')
	search_fields = ('email', 'first_name', 'last_name')
	ordering = ('email',)
	filter_horizontal = ('roles', 'groups', 'user_permissions')


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'estado')
	list_filter = ('estado',)
	search_fields = ('nombre',)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
	list_display = ('nombre', 'funciones')
	search_fields = ('nombre', 'funciones__nombre')


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
	list_display = ('nombre',)
	search_fields = ('nombre',)


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
