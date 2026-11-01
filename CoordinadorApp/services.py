from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count
from django.utils import timezone

from AdminApp.audit import registrar_historial
from AdminApp.models import ParametroSistema
from CoordinadorApp.models import Desempeno, SolicitudAutorizacionPeriodo
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia


ZERO = Decimal('0.00')
HUNDRED = Decimal('100')
META_SCOPE = 'metas'


def max_dias_autorizacion():
    return int(ParametroSistema.obtener(ParametroSistema.Clave.MAX_DIAS_AUTORIZACION))


def _authorization_snapshot(request):
    return {
        'periodo': request.periodo_id,
        'solicitante': request.solicitante_id,
        'funcionarios': list(request.funcionarios.values_list('pk', flat=True)),
        'alcances': request.alcances,
        'estado': request.estado,
        'vence_en': request.vence_en.isoformat() if request.vence_en else None,
        'usada_en': request.usada_en.isoformat() if request.usada_en else None,
        'revocada_en': request.revocada_en.isoformat() if request.revocada_en else None,
    }


def expire_authorizations():
    now = timezone.now()
    queryset = SolicitudAutorizacionPeriodo.objects.filter(
        estado=SolicitudAutorizacionPeriodo.Estado.APROBADA,
        vence_en__lte=now,
    ).select_related('periodo').prefetch_related('funcionarios')
    for authorization in queryset:
        before = _authorization_snapshot(authorization)
        authorization.estado = SolicitudAutorizacionPeriodo.Estado.VENCIDA
        authorization.save(update_fields=['estado'])
        registrar_historial(
            actor=authorization.aprobador or authorization.solicitante,
            action='Vencer autorizaciÃ³n de perÃ­odo',
            entity=f'SolicitudAutorizacionPeriodo:{authorization.pk}',
            before=before,
            after=_authorization_snapshot(authorization),
            period=authorization.periodo,
        )


def authorization_for(actor, period, scope=META_SCOPE, funcionario=None):
    expire_authorizations()
    now = timezone.now()
    candidates = SolicitudAutorizacionPeriodo.objects.filter(
        solicitante=actor,
        periodo=period,
        estado=SolicitudAutorizacionPeriodo.Estado.APROBADA,
        vence_en__gt=now,
    ).prefetch_related('funcionarios')
    for authorization in candidates:
        if scope not in (authorization.alcances or []):
            continue
        if funcionario is not None and not authorization.funcionarios.filter(pk=funcionario.pk).exists():
            continue
        return authorization
    return None


def record_authorization_use(authorization, actor):
    if authorization.usada_en is None:
        before = _authorization_snapshot(authorization)
        authorization.usada_en = timezone.now()
        authorization.save(update_fields=['usada_en'])
        registrar_historial(
            actor=actor,
            action='Usar autorizaciÃ³n de perÃ­odo por primera vez',
            entity=f'SolicitudAutorizacionPeriodo:{authorization.pk}',
            before=before,
            after=_authorization_snapshot(authorization),
            period=authorization.periodo,
        )


def validate_authorization_expiry(vence_en):
    if vence_en is None:
        return 'La fecha de vencimiento es obligatoria.'
    if vence_en <= timezone.now():
        return 'La fecha de vencimiento debe estar en el futuro.'
    maximum = timezone.now() + timedelta(days=max_dias_autorizacion())
    if vence_en > maximum:
        return f'La autorización no puede superar {max_dias_autorizacion()} días.'
    return ''


def umbral_delegacion():
    return ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION)


def clasificar_umbral(cumplimiento, *, tiene_items=True, umbral=None):
    if not tiene_items:
        return None
    return 'sobre' if Decimal(cumplimiento) >= (umbral if umbral is not None else umbral_delegacion()) else 'bajo'


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


def resumen_cumplimiento(desempenos, *, hoy=None, counts=None, cap=None):
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

    if counts is None:
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
    cap = Decimal(cap if cap is not None else ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO))

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


def tendencias_cumplimiento(usuarios, periodos, *, cap, umbral):
    usuarios = list(usuarios)
    periodos = list(periodos)
    if not usuarios or not periodos:
        return []

    user_ids = {usuario.pk for usuario in usuarios}
    period_ids = {periodo.pk for periodo in periodos}
    desempenos = list(
        Desempeno.objects.filter(
            usuario_id__in=user_ids,
            periodo_id__in=period_ids,
        ).select_related('item', 'periodo', 'usuario'),
    )
    counts = {
        (row['autor_id'], row['item_id'], row['periodo_id']): Decimal(row['cantidad'])
        for row in Registro.objects.filter(
            autor_id__in=user_ids,
            periodo_id__in=period_ids,
            estado=Registro.Estado.VALIDADA,
            evidencias_registros__estado=Evidencia.Estado.APROBADA,
        ).values('autor_id', 'item_id', 'periodo_id').annotate(
            cantidad=Count('pk', distinct=True),
        )
    }

    performances_by_user_period = defaultdict(list)
    for desempenho in desempenos:
        performances_by_user_period[
            (desempenho.usuario_id, desempenho.periodo_id)
        ].append(desempenho)

    series = []
    for periodo in periodos:
        total_avance_real = ZERO
        considerados = 0
        sobre_umbral = 0
        for usuario in usuarios:
            summary = resumen_cumplimiento(
                performances_by_user_period.get((usuario.pk, periodo.pk), ()),
                counts=counts,
                cap=cap,
            )
            if not summary['items']:
                continue
            considerados += 1
            total_avance_real += summary['avance_real']
            if clasificar_umbral(
                summary['avance_real'],
                tiene_items=True,
                umbral=umbral,
            ) == 'sobre':
                sobre_umbral += 1

        promedio = (
            total_avance_real / Decimal(considerados)
            if considerados else ZERO
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        porcentaje_sobre = (
            Decimal(sobre_umbral) * HUNDRED / Decimal(considerados)
            if considerados else ZERO
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        series.append({
            'periodo': periodo,
            'funcionarios_considerados': considerados,
            'promedio_avance_real': promedio,
            'porcentaje_sobre_umbral': porcentaje_sobre,
            'funcionarios_sin_items': len(usuarios) - considerados,
        })
    return series
