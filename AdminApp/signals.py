from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import signals
from django.dispatch import receiver

from AdminApp.models import Rol, Usuario, UsuarioRol
from AdminApp.roles import synchronize_user_role_groups
from config.permissions import PERMISSION_CATALOG


@receiver(signals.post_migrate)
def provision_catalog_permissions(sender, using, **kwargs):
    if sender.name != 'AdminApp':
        return

    content_type = ContentType.objects.db_manager(using).get_for_model(Rol)
    permissions = Permission.objects.using(using)
    for definition in PERMISSION_CATALOG:
        permissions.get_or_create(
            content_type=content_type,
            codename=definition.codename,
            defaults={'name': definition.label},
        )


@receiver(signals.post_save, sender=Rol)
def synchronize_users_after_role_change(sender, instance, using='default', **kwargs):
    user_ids = UsuarioRol.objects.using(using).filter(
        rol=instance,
        fecha_fin__isnull=True,
    ).values_list('usuario_id', flat=True).distinct()
    for user in Usuario.objects.using(using).filter(pk__in=user_ids):
        synchronize_user_role_groups(user)


@receiver(signals.pre_delete, sender=Group)
def prevent_deleting_protected_role_group(sender, instance, **kwargs):
    role = getattr(instance, 'rol_sgr', None)
    if role and role.protegido:
        raise ValidationError('No se puede eliminar el grupo de un rol protegido.')


@receiver(signals.pre_save, sender=Group)
def prevent_renaming_protected_role_group(sender, instance, **kwargs):
    if not instance.pk:
        return
    role = getattr(instance, 'rol_sgr', None)
    if role and role.protegido:
        previous_name = Group.objects.filter(pk=instance.pk).values_list(
            'name',
            flat=True,
        ).first()
        if previous_name != instance.name:
            raise ValidationError(
                'No se puede renombrar el grupo de un rol protegido.'
            )


@receiver(signals.m2m_changed, sender=Group.permissions.through)
def prevent_editing_protected_role_permissions(
    sender,
    instance,
    action,
    **kwargs,
):
    if action not in {'pre_add', 'pre_remove', 'pre_clear'}:
        return
    role = getattr(instance, 'rol_sgr', None)
    if role and role.protegido:
        raise ValidationError(
            'No se pueden modificar los permisos de un rol protegido.'
        )
