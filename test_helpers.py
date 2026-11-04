from django.contrib.auth import get_user_model

from AdminApp.models import UsuarioCargo, UsuarioDelegacion


def create_user(*, email, password, cargo=None, delegacion=None, **extra_fields):
    user = get_user_model().objects.create_user(
        email=email,
        password=password,
        **extra_fields,
    )
    if cargo is not None:
        UsuarioCargo.objects.create(usuario=user, cargo=cargo)
    if delegacion is not None:
        UsuarioDelegacion.objects.create(usuario=user, delegacion=delegacion)
    return user
