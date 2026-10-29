from django.contrib.auth.models import Group


def is_system_administrator(user):
    cargo = getattr(user, 'cargo', None)
    return bool(
        getattr(user, 'is_superuser', False)
        or (
            cargo
            and cargo.nombre.strip().casefold() in {'admin', 'administrador'}
        )
    )


def permission_codenames_for(user):
    return {
        permission.partition('.')[2]
        for permission in user.get_all_permissions()
        if permission.partition('.')[0] == 'AdminApp'
    }


def assignable_role_ids(actor, user=None):
    from AdminApp.models import Rol

    if is_system_administrator(actor):
        return None
    existing_role_ids = set(
        user.roles.values_list('pk', flat=True)
    ) if user and user.pk else set()
    actor_permissions = permission_codenames_for(actor)
    allowed_ids = set(existing_role_ids)
    roles = Rol.objects.filter(
        estado=Rol.Estado.ACTIVO,
    ).prefetch_related('grupo__permissions')
    for role in roles:
        role_permissions = (
            {
                permission.codename
                for permission in role.grupo.permissions.all()
            }
            if role.grupo_id else set()
        )
        if role_permissions.issubset(actor_permissions):
            allowed_ids.add(role.pk)
    return allowed_ids


def ensure_role_group(role):
    group, _ = Group.objects.get_or_create(name=f'sgr-role-{role.pk}')
    if role.grupo_id != group.pk:
        role.grupo = group
        role.save(update_fields=['grupo'])
    return group


def synchronize_user_role_groups(user):
    active_roles = user.roles.filter(estado='activo')
    assigned_groups = [
        ensure_role_group(role)
        for role in active_roles
    ]
    if assigned_groups:
        user.groups.add(*assigned_groups)

    stale_role_groups = Group.objects.filter(
        user=user,
        rol_sgr__isnull=False,
    ).exclude(pk__in=[group.pk for group in assigned_groups])
    if stale_role_groups.exists():
        user.groups.remove(*stale_role_groups)
