from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import signals
from django.dispatch import receiver

from AdminApp.models import Rol, Usuario
from AdminApp.roles import synchronize_user_role_groups


@receiver(signals.m2m_changed, sender=Usuario.roles.through)
def synchronize_role_groups(sender, instance, action, **kwargs):
    if action not in {'post_add', 'post_remove', 'post_clear'}:
        return

    synchronize_user_role_groups(instance)


@receiver(signals.post_save, sender=Rol)
def synchronize_users_after_role_change(sender, instance, **kwargs):
    for user in instance.usuarios.all():
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
