from AdminApp.models import Historial


def registrar_historial(*, actor, action, entity, before=None, after=None, period=None):
    return Historial.objects.create(
        autor=actor,
        accion=action,
        entidad_afectada=entity,
        valor_anterior=before,
        valor_nuevo=after,
        periodo=period,
    )
