from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

#Modelo Usuario
class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El correo electrónico es obligatorio.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Un superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Un superusuario debe tener is_superuser=True.')
        return self.create_user(email, password, **extra_fields)


# Modelo Delegación 
class Delegacion(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "Delegación"
        ordering = ['nombre']
        verbose_name = 'delegación'
        verbose_name_plural = 'delegaciones'

    def __str__(self):
        return self.nombre


#Modelo del Cargo
class Cargo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    funciones = models.ForeignKey(
        'CoordinadorApp.Funcion', on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        db_table = "Cargo"
        ordering = ['nombre']
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.nombre


#Modelo del Rol
class Rol(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    permisos = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "Rol"
        ordering = ['nombre']
        verbose_name = "Rol"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre

#Modelo del Usuario
class Usuario(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    objects = UsuarioManager()
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT,related_name='usuarios',null=True,blank=True)
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='usuarios', null=True, blank=True)
    roles = models.ManyToManyField(Rol, related_name='usuarios', blank=True)

    #Username Email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "Usuario"
        ordering = ['email']
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.get_full_name() or self.email


#Modelo del Catálogo
class Catalogo(models.Model):
    actividad = models.CharField(max_length=120, blank=True)
    servicio = models.CharField(max_length=120, blank=True)
    tipo = models.CharField(max_length=120, blank=True)
    subtipo = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['actividad', 'servicio', 'tipo', 'subtipo']
        db_table = "Catalogo"
        verbose_name = "Catálogo"
        verbose_name_plural = "Catálogos"

    def __str__(self):
        values = (self.actividad, self.servicio, self.tipo, self.subtipo)
        return ' / '.join(value for value in values if value)


#Modelo del Historial
class Historial(models.Model):
    autor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT, related_name='historiales')
    fecha_modificacion = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=120)
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)
    object_id = models.CharField(max_length=64)
    periodo = models.ForeignKey(
        'CoordinadorApp.Periodo', on_delete=models.SET_NULL, related_name='historiales',
        null=True, blank=True,
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    entidad_afectada = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-fecha_modificacion']
        db_table = "Historial"
        verbose_name = "Historial"
        verbose_name_plural = "Registros_Historial"

    def __str__(self):
        return f'{self.accion} ({self.fecha_modificacion:%Y-%m-%d %H:%M})'

