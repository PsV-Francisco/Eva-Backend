from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

#Modelo Usuario Abstracto
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
    estado = models.CharField(max_length=20, default='activa')

    class Meta:
        db_table = "delegación"
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
        db_table = "cargo"
        ordering = ['nombre']
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.nombre


#Modelo del Rol
class Rol(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    permisos = models.CharField(blank=True,max_length=1000)

    class Meta:
        db_table = "rol"
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
        db_table = "usuario"
        ordering = ['email']
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def crearResumenEjecutivo(self, periodo=None):
        #Importaciones
        from decimal import Decimal, ROUND_HALF_UP
        from django.db.models import Count, Q
        from CoordinadorApp.models import Desempeno, Periodo
        from DelegadoApp.models import Compromiso
        from FuncionarioApp.models import Registro
        from SupervisorApp.models import Evidencia

        if periodo is None:
            periodo_actual = Periodo.objects.filter(
                estado=Periodo.Estado.ABIERTO,
            ).first()
        else:
            periodo_actual = Periodo.objects.filter(
                pk=getattr(periodo, 'pk', periodo),
            ).first()

        if self.delegacion_id and periodo_actual:
            registros = Registro.objects.filter(
                autor__delegacion_id=self.delegacion_id,
                periodo=periodo_actual,
            ).select_related('autor', 'item', 'periodo')
            desempenos = Desempeno.objects.filter(
                usuario__delegacion_id=self.delegacion_id,
                periodo=periodo_actual,
            ).select_related('usuario', 'item', 'periodo')
            compromisos = Compromiso.objects.filter(
                agenda__delegacion_id=self.delegacion_id,
                agenda__periodo=periodo_actual,
            ).select_related('agenda', 'agenda__periodo').prefetch_related('responsables')
            evidencias = Evidencia.objects.filter(
                estado=Evidencia.Estado.PENDIENTE,
            ).filter(
                Q(
                    registro__autor__delegacion_id=self.delegacion_id,
                    registro__periodo=periodo_actual,
                )
                | Q(
                    compromiso__agenda__delegacion_id=self.delegacion_id,
                    compromiso__agenda__periodo=periodo_actual,
                )
            )
            funcionarios_activos = self.__class__.objects.filter(
                delegacion_id=self.delegacion_id,
                is_active=True,
            ).count()
        else:
            registros = Registro.objects.none()
            desempenos = Desempeno.objects.none()
            compromisos = Compromiso.objects.none()
            evidencias = Evidencia.objects.none()
            funcionarios_activos = 0

        compromisos_por_estado = dict(Compromiso.Estado.choices)
        compromisos_por_estado = {estado: 0 for estado in compromisos_por_estado}
        for resultado in compromisos.values('estado').annotate(total=Count('pk')):
            compromisos_por_estado[resultado['estado']] = resultado['total']

        compromisos_total = sum(compromisos_por_estado.values())
        compromisos_realizados = compromisos_por_estado[Compromiso.Estado.REALIZADO]
        porcentaje_compromisos_realizados = (
            (Decimal(compromisos_realizados) * Decimal('100') / Decimal(compromisos_total))
            .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if compromisos_total else Decimal('0.00')
        )

        cumplimiento_por_funcionario = {}
        for usuario_id, meta, avance, ponderacion in desempenos.values_list(
            'usuario_id', 'meta', 'avance', 'ponderacion',
        ):
            if meta:
                aporte_ponderado = avance * ponderacion / meta
                cumplimiento_por_funcionario[usuario_id] = (
                    cumplimiento_por_funcionario.get(usuario_id, Decimal('0'))
                    + aporte_ponderado
                )
        cumplimiento_ponderado_promedio = (
            (sum(cumplimiento_por_funcionario.values()) / len(cumplimiento_por_funcionario))
            .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if cumplimiento_por_funcionario else Decimal('0.00')
        )

        return {
            'periodo': periodo_actual,
            'delegacion': self.delegacion,
            'indicadores': {
                'funcionarios_activos': funcionarios_activos,
                'actividades': registros.count(),
                'actividades_validadas': registros.filter(
                    estado=Registro.Estado.VALIDADA,
                ).count(),
                'compromisos': compromisos_total,
                'compromisos_realizados': compromisos_realizados,
                'porcentaje_compromisos_realizados': porcentaje_compromisos_realizados,
                'compromisos_por_estado': compromisos_por_estado,
                'evidencias_pendientes': evidencias.count(),
                'desempenos': desempenos.count(),
                'cumplimiento_ponderado_promedio': cumplimiento_ponderado_promedio,
            },
            'detalle': {
                'registros': registros,
                'compromisos': compromisos,
                'desempenos': desempenos,
                'evidencias_pendientes': evidencias,
            },
        }

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
        db_table = "catalogo"
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
    periodo = models.ForeignKey(
        'CoordinadorApp.Periodo', on_delete=models.CASCADE, related_name='historiales',
        null=True, blank=True,
    )
    entidad_afectada = models.CharField(max_length=120, default='')

    class Meta:
        ordering = ['-fecha_modificacion']
        db_table = "historial"
        verbose_name = "Historial"
        verbose_name_plural = "Registros_Historial"

    def __str__(self):
        return f'{self.accion} ({self.fecha_modificacion:%Y-%m-%d %H:%M})'

