from django.http import Http404

from AdminApp.models import Delegacion
from AdminApp.roles import is_system_administrator
from config.delegations import active_delegation, authorized_delegations


def available_delegations(user):
    if is_system_administrator(user):
        return Delegacion.objects.order_by('nombre')
    return authorized_delegations(user)


def selected_delegation(request):
    raw_value = request.GET.get('delegacion', '').strip()
    is_admin = is_system_administrator(request.user)

    if raw_value in {'', 'todas'}:
        if is_admin:
            return None
        if raw_value == 'todas':
            raise Http404
        return active_delegation(request)

    if not raw_value.isdecimal():
        raise Http404

    delegation = available_delegations(request.user).filter(
        pk=raw_value,
    ).first()
    if delegation is None:
        raise Http404
    return delegation


def filter_by_delegation(
    queryset,
    request,
    *,
    delegation_lookup='delegacion_id',
    assignment_lookup=None,
):
    delegation = selected_delegation(request)
    if delegation is None:
        return queryset if is_system_administrator(request.user) else queryset.none()

    filters = {delegation_lookup: delegation.pk}
    if assignment_lookup:
        filters[f'{assignment_lookup}__fecha_fin__isnull'] = True
    return queryset.filter(**filters).distinct()
