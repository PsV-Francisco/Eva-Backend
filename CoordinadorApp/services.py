from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count
from django.utils import timezone

from AdminApp.models import ParametroSistema
from CoordinadorApp.models import Desempeno
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


ZERO = Decimal('0.00')
HUNDRED = Decimal('100')


def umbral_delegacion():
    return ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION)


def clasificar_umbral(cumplimiento, *, tiene_items=True):
    if not tiene_items:
        return None
    return 'sobre' if Decimal(cumplimiento) >= umbral_delegacion() else 'bajo'


def dias_habiles(inicio, termino):
    if termino < inicio:
        return 0
    total = 0
    current = inicio
    while current <= termino:
        if current.weekday() < 5:
            total += 1
        current += timedelta(days=1)
    return total


def porcentaje_esperado(periodo, *, hoy=None):
    hoy = hoy or timezone.localdate()
    total = dias_habiles(periodo.fecha_inicio, periodo.fecha_fin)
    if not total or hoy < periodo.fecha_inicio:
        return ZERO
    transcurridos = dias_habiles(
        periodo.fecha_inicio,
        min(hoy, periodo.fecha_fin),
    )
    return (Decimal(transcurridos) * HUNDRED / Decimal(total)).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )


def _semaforo(cumplimiento, esperado):
    if cumplimiento >= esperado:
        return 'verde'
    if cumplimiento >= esperado * Decimal('0.60'):
        return 'ambar'
    return 'rojo'


def resumen_cumplimiento(desempenos, *, hoy=None):
    desempenos = list(desempenos)
    if not desempenos:
        return {
            'items': [],
            'total_avance': ZERO,
            'total_meta': ZERO,
            'avance_real': ZERO,
            'avance_esperado': ZERO,
            'total_aporte': ZERO,
        }

    registros_aprobados = Registro.objects.filter(
        autor_id__in={row.usuario_id for row in desempenos},
        periodo_id__in={row.periodo_id for row in desempenos},
        estado=Registro.Estado.VALIDADA,
        evidencias_registros__estado=Evidencia.Estado.APROBADA,
    ).values('autor_id', 'item_id', 'periodo_id').annotate(
        cantidad=Count('pk', distinct=True),
    )
    counts = {
        (row['autor_id'], row['item_id'], row['periodo_id']): Decimal(row['cantidad'])
        for row in registros_aprobados
    }
    cap = Decimal(ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO))

    items = []
    total_avance = ZERO
    total_meta = ZERO
    total_esperado = ZERO
    total_aporte = ZERO
    for desempenho in desempenos:
        avance = counts.get(
            (desempenho.usuario_id, desempenho.item_id, desempenho.periodo_id),
            ZERO,
        )
        meta = Decimal(desempenho.meta)
        cumplimiento = min(avance * HUNDRED / meta, cap).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )
        esperado = porcentaje_esperado(desempenho.periodo, hoy=hoy)
        aporte = (
            Decimal(desempenho.ponderacion) * cumplimiento / HUNDRED
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        expected_amount = meta * esperado / HUNDRED
        items.append({
            'desempeno': desempenho,
            'avance': avance,
            'meta': meta,
            'cumplimiento': cumplimiento,
            'esperado': esperado,
            'ponderacion': desempenho.ponderacion,
            'aporte': aporte,
            'semaforo': _semaforo(cumplimiento, esperado),
        })
        total_avance += avance
        total_meta += meta
        total_esperado += expected_amount
        total_aporte += aporte

    avance_real = (
        min(total_avance * HUNDRED / total_meta, cap)
        if total_meta else ZERO
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    avance_esperado = (
        total_esperado * HUNDRED / total_meta
        if total_meta else ZERO
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {
        'items': items,
        'total_avance': total_avance,
        'total_meta': total_meta,
        'avance_real': avance_real,
        'avance_esperado': avance_esperado,
        'total_aporte': total_aporte.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    }


def cumplimiento_por_usuario(desempenos, *, hoy=None):
    all_items = resumen_cumplimiento(desempenos, hoy=hoy)['items']
    by_user = defaultdict(list)
    for item in all_items:
        by_user[item['desempeno'].usuario_id].append(item)
    return {
        user_id: _resumen_desde_items(items)
        for user_id, items in by_user.items()
    }


def _resumen_desde_items(items):
    total_avance = sum((item['avance'] for item in items), ZERO)
    total_meta = sum((item['meta'] for item in items), ZERO)
    total_esperado = sum(
        (item['meta'] * item['esperado'] / HUNDRED for item in items),
        ZERO,
    )
    total_aporte = sum((item['aporte'] for item in items), ZERO)
    cap = Decimal(ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO))
    avance_real = min(total_avance * HUNDRED / total_meta, cap) if total_meta else ZERO
    avance_esperado = total_esperado * HUNDRED / total_meta if total_meta else ZERO
    return {
        'items': items,
        'total_avance': total_avance,
        'total_meta': total_meta,
        'avance_real': avance_real.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'avance_esperado': avance_esperado.quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        ),
        'total_aporte': total_aporte.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    }
