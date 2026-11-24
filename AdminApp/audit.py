from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import models

from AdminApp.models import Historial


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, models.Model):
        return {'model': value._meta.label, 'id': value.pk}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def registrar_historial(*, actor, action, entity, before=None, after=None, period=None):
    return Historial.objects.create(
        autor=actor,
        accion=action,
        entidad_afectada=entity,
        valor_anterior=_json_safe(before),
        valor_nuevo=_json_safe(after),
        periodo=period,
    )
