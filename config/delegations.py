from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from AdminApp.models import Delegacion


ACTIVE_DELEGATION_SESSION_KEY = 'active_delegation_id'


def authorized_delegations(user):
    if not user.is_authenticated:
        return Delegacion.objects.none()
    return Delegacion.objects.filter(
        usuariodelegacion__usuario=user,
        usuariodelegacion__fecha_fin__isnull=True,
        estado=Delegacion.Estado.ACTIVA,
    ).distinct().order_by('nombre')


def active_delegation(request):
    if not request.user.is_authenticated:
        return None

    if hasattr(request, '_active_delegation'):
        return request._active_delegation

    delegations = authorized_delegations(request.user)
    selected_id = request.session.get(ACTIVE_DELEGATION_SESSION_KEY)
    selected = (
        delegations.filter(pk=selected_id).first()
        if str(selected_id).isdecimal()
        else None
    )
    current_assignment = request.user.delegacion_actual
    if selected is None and current_assignment:
        selected = delegations.filter(
            pk=current_assignment.delegacion_id,
        ).first()
    if selected is None:
        selected = delegations.first()

    request._active_delegation = selected
    return selected


@login_required
@require_POST
def select_active_delegation(request):
    delegation_id = request.POST.get('delegacion')
    delegation = (
        authorized_delegations(request.user).filter(pk=delegation_id).first()
        if delegation_id and delegation_id.isdecimal()
        else None
    )
    if delegation is None:
        messages.error(request, 'No tienes autorización para esa delegación.')
    else:
        request.session[ACTIVE_DELEGATION_SESSION_KEY] = delegation.pk

    destination = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        destination, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        destination = reverse('home')
    return redirect(destination)
