from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from config.permissions import PERMISSION_CATALOG


CRITICAL_CARGO_NAMES = frozenset({
    'admin',
    'administrador',
    'coordinador',
    'delegado',
    'funcionario',
    'supervisor',
    'verificador',
    'vistaf',
    'consulta',
    'usuario de consulta',
})
PROTECTED_ROLE_NAMES = frozenset({
    'admin',
    'administrador',
    'administrador del sistema',
})


def is_critical_cargo_name(name):
    return (name or '').strip().casefold() in CRITICAL_CARGO_NAMES


class CargoQuerySet(models.QuerySet):
    def delete(self):
        protected_cargos = [
            cargo for cargo in self
            if is_critical_cargo_name(cargo.nombre)
        ]
        if protected_cargos:
            raise ProtectedError(
                'Los cargos usados por los controles de acceso no se pueden eliminar.',
                protected_cargos,
            )
        return super().delete()


class CargoManager(models.Manager.from_queryset(CargoQuerySet)):
    pass


class RolQuerySet(models.QuerySet):
    def update(self, **kwargs):
        protected_fields = {
            'nombre', 'descripcion', 'alcance', 'estado', 'protegido', 'grupo',
            'grupo_id',
        }
        if protected_fields.intersection(kwargs) and self.filter(
            protegido=True,
        ).exists():
            raise ValidationError(
                'Un rol protegido no se puede modificar ni desproteger.'
            )
        return super().update(**kwargs)

    def delete(self):
        protected_roles = [
            role for role in self
            if role.protegido or role.usuarios.exists()
        ]
        if protected_roles:
            raise ProtectedError(
                'Los roles protegidos o asignados no se pueden eliminar.',
                protected_roles,
            )
        return super().delete()


class RolManager(models.Manager.from_queryset(RolQuerySet)):
    pass


def _administrator_accounts():
    return (
        Q(is_superuser=True)
        | Q(cargo__nombre__iexact='admin')
        | Q(cargo__nombre__iexact='administrador')
    )


class UsuarioQuerySet(models.QuerySet):
    def update(self, **kwargs):
        protected_fields = {'cargo', 'cargo_id', 'is_active', 'is_superuser'}
        if protected_fields.intersection(kwargs) and self.filter(
            is_active=True,
        ).filter(_administrator_accounts()).exists():
            raise ValidationError(
                'La administración de cuentas con privilegios requiere guardar '
                'cada cuenta individualmente para proteger al último Administrador.'
            )
        return super().update(**kwargs)

    def delete(self):
        active_admins = self.filter(is_active=True).filter(
            _administrator_accounts(),
        )
        total_admins = self.model._default_manager.filter(
            is_active=True,
        ).filter(_administrator_accounts()).count()
        if total_admins and active_admins.count() >= total_admins:
            raise ProtectedError(
                'No se puede eliminar el último Administrador activo.',
                list(active_admins),
            )
        return super().delete()


#Modelo Usuario Abstracto
class UsuarioManager(BaseUserManager):
    use_in_migrations = True
    _queryset_class = UsuarioQuerySet

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
    class Estado(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        INACTIVA = 'inactiva', 'Inactiva'

    codigo = models.CharField(max_length=20, unique=True, null=True)
    nombre = models.CharField(max_length=120, unique=True)
    direccion = models.CharField(max_length=255, blank=True)
    comuna = models.CharField(max_length=120, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA,
    )

    class Meta:
        db_table = "delegación"
        ordering = ['nombre']
        verbose_name = 'delegación'
        verbose_name_plural = 'delegaciones'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.codigo and self.pk is None:
            super().save(*args, **kwargs)
            self.codigo = f'DEL-{self.pk:04d}'
            super().save(using=kwargs.get('using'), update_fields=['codigo'])
            return
        return super().save(*args, **kwargs)


#Modelo del Cargo
class Cargo(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    nombre = models.CharField(max_length=120, unique=True)
    funciones = models.ForeignKey(
        'CoordinadorApp.Funcion', on_delete=models.PROTECT, null=True, blank=True
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )
    objects = CargoManager()

    class Meta:
        db_table = "cargo"
        ordering = ['nombre']
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        if not self.pk:
            return
        previous_name = type(self).objects.filter(pk=self.pk).values_list(
            'nombre', flat=True,
        ).first()
        if (
            previous_name
            and is_critical_cargo_name(previous_name)
            and self.nombre != previous_name
        ):
            raise ValidationError({
                'nombre': 'No se puede renombrar un cargo usado por el control de acceso.',
            })

    def save(self, *args, **kwargs):
        if self.pk:
            previous_name = type(self).objects.filter(pk=self.pk).values_list(
                'nombre', flat=True,
            ).first()
            if (
                previous_name
                and is_critical_cargo_name(previous_name)
                and self.nombre != previous_name
            ):
                raise ValidationError(
                    'No se puede renombrar un cargo usado por el control de acceso.'
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if is_critical_cargo_name(self.nombre):
            raise ProtectedError(
                'Los cargos usados por los controles de acceso no se pueden eliminar.',
                [self],
            )
        return super().delete(*args, **kwargs)


#Modelo del Rol
class Rol(models.Model):
    class Alcance(models.TextChoices):
        GLOBAL = 'global', 'Global'
        DELEGACION = 'delegacion', 'Delegación'

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    nombre = models.CharField(max_length=80, unique=True)
    permisos = models.CharField(blank=True,max_length=1000)
    descripcion = models.TextField(blank=True)
    grupo = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name='rol_sgr',
        null=True,
        blank=True,
    )
    protegido = models.BooleanField(default=False)
    alcance = models.CharField(
        max_length=20,
        choices=Alcance.choices,
        default=Alcance.GLOBAL,
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )

    class Meta:
        db_table = "rol"
        ordering = ['nombre']
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        permissions = tuple(
            (permission.codename, permission.label)
            for permission in PERMISSION_CATALOG
        )
    objects = RolManager()

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        normalized_name = self.nombre.strip().casefold()
        if not self.pk and normalized_name in PROTECTED_ROLE_NAMES:
            raise ValidationError(
                'El nombre está reservado para roles críticos del sistema.'
            )
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.protegido and (
                self.nombre != previous.nombre
                or self.descripcion != previous.descripcion
                or self.alcance != previous.alcance
                or self.estado != previous.estado
                or self.protegido != previous.protegido
                or (
                    previous.grupo_id is not None
                    and self.grupo_id != previous.grupo_id
                )
            ):
                raise ValidationError(
                    'Un rol protegido no se puede modificar ni desproteger.'
                )
            if (
                previous
                and normalized_name in PROTECTED_ROLE_NAMES
                and normalized_name != previous.nombre.strip().casefold()
            ):
                raise ValidationError(
                    'El nombre está reservado para roles críticos del sistema.'
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.protegido or self.usuarios.exists():
            raise ProtectedError(
                'Los roles protegidos o asignados no se pueden eliminar.',
                [self],
            )
        return super().delete(*args, **kwargs)

#Modelo del Usuario
class Usuario(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    objects = UsuarioManager()
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT,related_name='usuarios',null=True,blank=True)
    delegaciones_autorizadas = models.ManyToManyField(
        Delegacion, related_name='usuarios_autorizados', blank=True,
    )
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

    def save(self, *args, **kwargs):
        if self.pk:
            using = kwargs.get('using') or self._state.db or 'default'
            with transaction.atomic(using=using):
                administrators = type(self).objects.using(using).select_for_update().filter(
                    is_active=True,
                ).filter(_administrator_accounts())
                previous = administrators.filter(pk=self.pk).exists()
                remains_administrator = self.is_active and (
                    self.is_superuser
                    or (
                        self.cargo
                        and self.cargo.nombre.strip().casefold()
                        in {'admin', 'administrador'}
                    )
                )
                if previous and not remains_administrator and administrators.count() <= 1:
                    raise ValidationError(
                        'No se puede desactivar, eliminar o degradar al último '
                        'Administrador activo.'
                    )
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        using = kwargs.get('using') or self._state.db or 'default'
        with transaction.atomic(using=using):
            administrators = type(self).objects.using(using).select_for_update().filter(
                is_active=True,
            ).filter(_administrator_accounts())
            if administrators.filter(pk=self.pk).exists() and administrators.count() <= 1:
                raise ProtectedError(
                    'No se puede eliminar al último Administrador activo.',
                    [self],
                )
            return super().delete(*args, **kwargs)

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
    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    actividad = models.CharField(max_length=120, blank=True)
    servicio = models.CharField(max_length=120, blank=True)
    tipo = models.CharField(max_length=120, blank=True)
    subtipo = models.CharField(max_length=120, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )

    class Meta:
        ordering = ['actividad', 'servicio', 'tipo', 'subtipo']
        db_table = "catalogo"
        verbose_name = "Catálogo"
        verbose_name_plural = "Catálogos"

    def __str__(self):
        values = (self.actividad, self.servicio, self.tipo, self.subtipo)
        return ' / '.join(value for value in values if value)


class TipoAtencion(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )

    class Meta:
        ordering = ['nombre']
        verbose_name = 'tipo de atención'
        verbose_name_plural = 'tipos de atención'

    def __str__(self):
        return self.nombre


class SubAtencion(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    tipo_atencion = models.ForeignKey(
        TipoAtencion,
        on_delete=models.PROTECT,
        related_name='subatenciones',
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )

    class Meta:
        ordering = ['tipo_atencion__nombre', 'nombre']
        constraints = [
            models.UniqueConstraint(
                fields=['tipo_atencion', 'nombre'],
                name='sub_atencion_nombre_unico_por_tipo',
            ),
        ]
        verbose_name = 'sub atención'
        verbose_name_plural = 'sub atenciones'

    def __str__(self):
        return f'{self.tipo_atencion}: {self.nombre}'


#Modelo del Historial
class Historial(models.Model):
    autor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT, related_name='historiales')
    fecha_modificacion = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=120)
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)
    periodo = models.ForeignKey(
        'CoordinadorApp.Periodo', on_delete=models.SET_NULL, related_name='historiales',
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


class PasswordResetAuditEvent(models.Model):
    class Action(models.TextChoices):
        REQUEST = 'request', 'Solicitud de recuperación'
        CODE_VALIDATION = 'code_validation', 'Validación de código'
        PASSWORD_CHANGED = 'password_changed', 'Contraseña actualizada'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='password_reset_events',
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    email_fingerprint = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    was_rate_limited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_audit'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['action', 'email_fingerprint', 'created_at'],
                name='pwd_reset_email_idx',
            ),
            models.Index(
                fields=['action', 'ip_address', 'created_at'],
                name='pwd_reset_ip_idx',
            ),
        ]
        verbose_name = 'evento de recuperación de contraseña'
        verbose_name_plural = 'eventos de recuperación de contraseña'

    def __str__(self):
        return f'{self.get_action_display()} ({self.created_at:%Y-%m-%d %H:%M})'


class PasswordResetCode(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_code',
    )
    email_fingerprint = models.CharField(max_length=64, db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_sent_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'password_reset_code'
        verbose_name = 'código de recuperación'
        verbose_name_plural = 'códigos de recuperación'


class PasswordResetRateLimitKey(models.Model):
    key = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = 'password_reset_rate_limit_key'


class ParametroSistema(models.Model):
    class Clave(models.TextChoices):
        MAX_DIAS_AUTORIZACION = 'max_dias_autorizacion', 'Maximo de dias de autorizacion'
        TOPE_CUMPLIMIENTO = 'tope_cumplimiento', 'Tope de cumplimiento (%)'
        UMBRAL_DELEGACION = 'umbral_delegacion', 'Umbral de delegación (%)'

    clave = models.CharField(max_length=40, choices=Clave.choices, unique=True)
    valor = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ['clave']
        verbose_name = 'parámetro del sistema'
        verbose_name_plural = 'parámetros del sistema'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(clave='tope_cumplimiento', valor__gte=100)
                    | models.Q(clave='umbral_delegacion', valor__gte=0, valor__lte=100)
                    | models.Q(clave='max_dias_autorizacion', valor__gte=1, valor__lte=365)
                ),
                name='parametro_sistema_valor_en_rango',
            ),
        ]

    def __str__(self):
        return f'{self.get_clave_display()}: {self.valor}%'

    @classmethod
    def obtener(cls, clave):
        defaults = {
            cls.Clave.TOPE_CUMPLIMIENTO: 150,
            cls.Clave.UMBRAL_DELEGACION: 80,
            cls.Clave.MAX_DIAS_AUTORIZACION: 7,
        }
        value = cls.objects.filter(clave=clave).values_list('valor', flat=True).first()
        return value if value is not None else defaults[clave]


class Alerta(models.Model):
    id = models.AutoField(primary_key=True, db_column='ID')
    motivo = models.CharField(max_length=100, db_column='MOTIVO')
    fecha = models.DateTimeField(db_column='FECHA')
    estado = models.CharField(max_length=50, db_column='ESTADO')
    enlace = models.CharField(
        max_length=500, null=True, blank=True, db_column='ENLACE',
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='alertas_recibidas',
        db_column='DESTINATARIO',
    )

    class Meta:
        db_table = 'alertas'
        verbose_name = 'alerta'
        verbose_name_plural = 'alertas'

    def __str__(self):
        return self.motivo


class Comentarios(models.Model):
    id = models.AutoField(primary_key=True, db_column='ID')
    texto = models.TextField(db_column='TEXTO')
    fecha = models.DateTimeField(db_column='FECHA')
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comentarios_escritos',
        db_column='AUTOR',
    )
    registro = models.ForeignKey(
        'FuncionarioApp.Registro',
        on_delete=models.PROTECT,
        related_name='comentarios_objetivo',
        db_column='REGISTRO',
        null=True,
        blank=True,
    )
    autor_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comentarios_como_autor_registro',
        db_column='AUTOR_REGISTRO',
        null=True,
        blank=True,
        editable=False,
    )
    item_registro = models.ForeignKey(
        'CoordinadorApp.Item',
        on_delete=models.PROTECT,
        related_name='comentarios_registro',
        db_column='ITEM_REGISTRO',
        null=True,
        blank=True,
        editable=False,
    )
    periodo_registro = models.ForeignKey(
        'CoordinadorApp.Periodo',
        on_delete=models.PROTECT,
        related_name='comentarios_registro',
        db_column='PERIODO_REGISTRO',
        null=True,
        blank=True,
        editable=False,
    )
    compromiso = models.ForeignKey(
        'DelegadoApp.Compromiso',
        on_delete=models.PROTECT,
        related_name='comentarios_objetivo',
        db_column='COMPROMISO',
        null=True,
        blank=True,
    )
    responsable_compromiso = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comentarios_como_responsable',
        db_column='RESPONSABLE_COMPROMISO',
        null=True,
        blank=True,
        editable=False,
    )
    agenda_compromiso = models.ForeignKey(
        'DelegadoApp.Agenda',
        on_delete=models.PROTECT,
        related_name='comentarios_compromiso',
        db_column='AGENDA_COMPROMISO',
        null=True,
        blank=True,
        editable=False,
    )
    periodo_agenda_compromiso = models.ForeignKey(
        'CoordinadorApp.Periodo',
        on_delete=models.PROTECT,
        related_name='comentarios_agenda_compromiso',
        db_column='PERIODO_AGENDA_COMPROMISO',
        null=True,
        blank=True,
        editable=False,
    )
    agenda_delegacion_compromiso = models.ForeignKey(
        'AdminApp.Delegacion',
        on_delete=models.PROTECT,
        related_name='comentarios_agenda_compromiso',
        db_column='AGENDA_DELEGACION_COMPROMISO',
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        db_table = 'comentarios'
        verbose_name = 'comentario'
        verbose_name_plural = 'comentarios'

    def clean(self):
        super().clean()
        if not self.registro_id and not self.compromiso_id:
            raise ValidationError(
                'El comentario debe estar asociado a un registro o compromiso.'
            )

        errors = {}
        registro_dimensions = {
            'autor_registro': self.registro.autor_id if self.registro_id else None,
            'item_registro': self.registro.item_id if self.registro_id else None,
            'periodo_registro': self.registro.periodo_id if self.registro_id else None,
        }
        for field_name, expected_id in registro_dimensions.items():
            value_id = getattr(self, f'{field_name}_id')
            if value_id is not None and value_id != expected_id:
                errors[field_name] = 'Debe coincidir con el registro relacionado.'

        if self.compromiso_id:
            compromiso = self.compromiso
            responsables = list(
                compromiso.responsables.values_list('pk', flat=True)[:2]
            )
            expected_responsable = responsables[0] if len(responsables) == 1 else None
            agenda = compromiso.agenda
            commitment_dimensions = {
                'responsable_compromiso': expected_responsable,
                'agenda_compromiso': agenda.pk,
                'periodo_agenda_compromiso': agenda.periodo_id,
                'agenda_delegacion_compromiso': agenda.delegacion_id,
            }
        else:
            commitment_dimensions = {
                'responsable_compromiso': None,
                'agenda_compromiso': None,
                'periodo_agenda_compromiso': None,
                'agenda_delegacion_compromiso': None,
            }

        for field_name, expected_id in commitment_dimensions.items():
            value_id = getattr(self, f'{field_name}_id')
            if value_id is not None and value_id != expected_id:
                errors[field_name] = 'Debe coincidir con el compromiso relacionado.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        derived_fields = (
            'autor_registro',
            'item_registro',
            'periodo_registro',
            'responsable_compromiso',
            'agenda_compromiso',
            'periodo_agenda_compromiso',
            'agenda_delegacion_compromiso',
        )
        if self.registro_id:
            self.autor_registro_id = self.registro.autor_id
            self.item_registro_id = self.registro.item_id
            self.periodo_registro_id = self.registro.periodo_id
        else:
            self.autor_registro_id = None
            self.item_registro_id = None
            self.periodo_registro_id = None

        if self.compromiso_id:
            compromiso = self.compromiso
            responsables = list(
                compromiso.responsables.values_list('pk', flat=True)[:2]
            )
            self.responsable_compromiso_id = (
                responsables[0] if len(responsables) == 1 else None
            )
            self.agenda_compromiso_id = compromiso.agenda_id
            self.periodo_agenda_compromiso_id = compromiso.agenda.periodo_id
            self.agenda_delegacion_compromiso_id = compromiso.agenda.delegacion_id
        else:
            self.responsable_compromiso_id = None
            self.agenda_compromiso_id = None
            self.periodo_agenda_compromiso_id = None
            self.agenda_delegacion_compromiso_id = None

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields).union(derived_fields)
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Comentario {self.pk}'
