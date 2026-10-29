from django.db import transaction

from AdminApp.audit import registrar_historial
from DelegadoApp.models import Compromiso, HistorialEstadoCompromiso


@transaction.atomic
def actualizar_estado_compromiso(*, compromiso, autor, nuevo_estado):
    estado_anterior = compromiso.estado
    if estado_anterior == nuevo_estado:
        return False

    compromiso.estado = nuevo_estado
    compromiso.save(update_fields=['estado'])
    HistorialEstadoCompromiso.objects.create(
        compromiso=compromiso,
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado,
        autor=autor,
    )
    registrar_historial(
        actor=autor,
        action='Cambiar estado de compromiso',
        entity=f'Compromiso:{compromiso.pk}',
        before={'estado': estado_anterior},
        after={'estado': nuevo_estado},
        period=compromiso.agenda.periodo,
    )
    return True
