#Importaciones de Django
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Count, Q
from django.utils import timezone
from AdminApp.audit import registrar_historial
#Importación de Modelos
from AdminApp.models import ParametroSistema
from CoordinadorApp.models import Desempeno, SolicitudAutorizacionPeriodo
from FuncionarioApp.models import Registro, limite_diario_actividades
from SupervisorApp.models import Evidencia
from DelegadoApp.models import Ausencia, Licencia


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
        vence_en__lte=now).select_related('periodo').prefetch_related('funcionarios')
    for authorization in queryset:
        before = _authorization_snapshot(authorization)
        authorization.estado = SolicitudAutorizacionPeriodo.Estado.VENCIDA
        authorization.save(update_fields=['estado'])
        registrar_historial(
            actor=authorization.aprobador or authorization.solicitante,
            action='Vencer autorización de período',
            entity=f'SolicitudAutorizacionPeriodo:{authorization.pk}',
            before=before,
            after=_authorization_snapshot(authorization),
            period=authorization.periodo,
        )


def authorization_for(actor, period, scope=META_SCOPE, funcionario=None):
    expire_authorizations()
    now = timezone.now()
    candidates = SolicitudAutorizacionPeriodo.objects.filter(solicitante=actor,periodo=period,estado=SolicitudAutorizacionPeriodo.Estado.APROBADA,vence_en__gt=now).prefetch_related('funcionarios')
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
            action='Usar autorización de período por primera vez',
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


def _dias_no_trabajados(periodo, usuario, inicio, termino):
    if usuario is None or termino < inicio:
        return 0

    inicio = max(inicio, periodo.fecha_inicio)
    termino = min(termino, periodo.fecha_fin)
    if termino < inicio:
        return 0

    licencia_days = 0
    for licencia in Licencia.objects.filter(usuario=usuario):
        licencia_inicio = licencia.fecha_inicio.date()
        licencia_fin = licencia.fecha_fin.date()
        licencia_inicio = max(licencia_inicio, inicio)
        licencia_fin = min(licencia_fin, termino)
        licencia_days += dias_habiles(licencia_inicio, licencia_fin)

    ausencia_days = set(
        ausencia.fecha.date()
        for ausencia in Ausencia.objects.filter(
            usuario=usuario,
            fecha__date__range=(inicio, termino),
        )
        if inicio <= ausencia.fecha.date() <= termino
        and ausencia.fecha.weekday() < 5
    )
    return licencia_days + len(ausencia_days)


def porcentaje_esperado(periodo, fecha_corte=None, usuario=None, *, hoy=None):
    fecha_corte = fecha_corte or hoy or timezone.localdate()
    total = dias_habiles(periodo.fecha_inicio, periodo.fecha_fin)
    if usuario is not None:
        total -= (getattr(usuario, 'dias_adm', 0) or 0)
        total -= (getattr(usuario, 'dias_libres', 0) or 0)
        total -= _dias_no_trabajados(
            periodo,
            usuario,
            periodo.fecha_inicio,
            periodo.fecha_fin,
        )
        total = max(total, 1)
    if not total or fecha_corte < periodo.fecha_inicio:
        return ZERO
    transcurridos = dias_habiles(periodo.fecha_inicio,min(fecha_corte, periodo.fecha_fin))
    if usuario is not None:
        transcurridos -= _dias_no_trabajados(periodo,usuario,periodo.fecha_inicio,min(fecha_corte, periodo.fecha_fin))
        transcurridos = max(transcurridos, 0)
    return (Decimal(transcurridos) * HUNDRED / Decimal(total)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)


def _semaforo(cumplimiento, esperado):
    if cumplimiento >= esperado:
        return 'verde'
    if cumplimiento >= esperado * Decimal('0.60'):
        return 'ambar'
    return 'rojo'


def _conteo_actividades_puntaje(user_ids, period_ids):
    """Cuenta actividades validadas con evidencia aprobada y genera_puntaje='SI', respetando el tope diario."""
    if not user_ids or not period_ids:
        return {}
    registros_qs = Registro.objects.filter(
        autor_id__in=user_ids,
        periodo_id__in=period_ids,
        estado=Registro.Estado.VALIDADA,
        evidencia__estado=Evidencia.Estado.APROBADA,).filter(Q(genera_puntaje__iexact='SI') | Q(genera_puntaje__isnull=True) | Q(genera_puntaje='')).select_related('autor').order_by('autor_id', 'fecha', 'creado', 'pk')

    diarios_por_usuario = defaultdict(int)
    counts = defaultdict(Decimal)
    for reg in registros_qs:
        limite = limite_diario_actividades(reg.autor)
        day_key = (reg.autor_id, reg.fecha)
        if diarios_por_usuario[day_key] >= limite:
            continue
        diarios_por_usuario[day_key] += 1
        counts[(reg.autor_id, reg.item_id, reg.periodo_id)] += Decimal('1')
    return dict(counts)

# Updated 17.11
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
            'total_ponderacion': ZERO,
            'ponderacion_completa': False,
        }

    if counts is None:
        counts = _conteo_actividades_puntaje(
            {row.usuario_id for row in desempenos},
            {row.periodo_id for row in desempenos},
        )
    cap = Decimal(cap if cap is not None else ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO))

    items = []
    total_avance = ZERO
    total_meta = ZERO
    total_esperado = ZERO
    total_aporte = ZERO
    total_ponderacion = ZERO  # <-- Añadido
    for desempenho in desempenos:
        avance = counts.get((desempenho.usuario_id, desempenho.item_id, desempenho.periodo_id),ZERO)
        meta = Decimal(desempenho.meta)
        cumplimiento = min(avance * HUNDRED / meta, cap).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        esperado = porcentaje_esperado(desempenho.periodo,fecha_corte=hoy,usuario=desempenho.usuario)
        ponderacion = desempenho.ponderacion
        aporte = ((Decimal(ponderacion) * cumplimiento / HUNDRED).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
            if ponderacion is not None else None)
        expected_amount = meta * esperado / HUNDRED
        items.append({'desempeno': desempenho,'avance': avance,'meta': meta,'cumplimiento': cumplimiento,'esperado': esperado,'ponderacion': ponderacion,'aporte': aporte,'semaforo': _semaforo(cumplimiento, esperado),})
        total_avance += avance
        total_meta += meta
        total_esperado += expected_amount
        if aporte is not None:
            total_aporte += aporte
        if ponderacion is not None:
            total_ponderacion += Decimal(ponderacion)  # <-- Añadido

    avance_real = (min(total_avance * HUNDRED / total_meta, cap)
        if total_meta else ZERO).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    avance_esperado = (total_esperado * HUNDRED / total_meta if total_meta else ZERO).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {
        'items': items,
        'total_avance': total_avance,
        'total_meta': total_meta,
        'avance_real': avance_real,
        'avance_esperado': avance_esperado,
        'total_aporte': total_aporte.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_ponderacion': total_ponderacion.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'ponderacion_completa': all(
            item['ponderacion'] is not None for item in items
        ),
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


def consolidar_cumplimientos(summaries, *, threshold=None):
    """Consolida funcionarios usando una única fórmula de promedio simple."""
    summaries = list(summaries)
    with_items = [summary for summary in summaries if summary['items']]
    collective = (
        sum((summary['avance_real'] for summary in with_items), ZERO)
        / Decimal(len(with_items))
        if with_items else ZERO
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    counts = {'verde': 0, 'ambar': 0, 'rojo': 0, 'sin_items': 0}
    for summary in summaries:
        if not summary['items']:
            counts['sin_items'] += 1
            continue
        state = _semaforo(summary['avance_real'], summary['avance_esperado'])
        counts[state] += 1
    total = Decimal(len(summaries))
    distribution = {
        state: {
            'count': count,
            'percentage': ((Decimal(count) * HUNDRED / total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP,) if total else ZERO)} for state, count in counts.items()}
    below = sum(1 for summary in with_items if threshold is not None and summary['avance_real'] < threshold)
    return {
        'total_funcionarios': len(summaries),
        'cumplimiento_colectivo': collective,
        'distribucion_semaforo': distribution,
        'cantidad_bajo_umbral': below,
    }


def _resumen_desde_items(items):
    total_avance = sum((item['avance'] for item in items), ZERO)
    total_meta = sum((item['meta'] for item in items), ZERO)
    total_esperado = sum((item['meta'] * item['esperado'] / HUNDRED for item in items),ZERO)
    total_aporte = sum((item['aporte'] for item in items if item['aporte'] is not None),ZERO)
    cap = Decimal(ParametroSistema.obtener(ParametroSistema.Clave.TOPE_CUMPLIMIENTO))
    avance_real = min(total_avance * HUNDRED / total_meta, cap) if total_meta else ZERO
    avance_esperado = total_esperado * HUNDRED / total_meta if total_meta else ZERO
    return {
        'items': items,
        'total_avance': total_avance,
        'total_meta': total_meta,
        'avance_real': avance_real.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'avance_esperado': avance_esperado.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),
        'total_aporte': total_aporte.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'ponderacion_completa': all(item['ponderacion'] is not None for item in items),}


def tendencias_cumplimiento(usuarios, periodos, *, cap, umbral):
    usuarios = list(usuarios)
    periodos = list(periodos)
    if not usuarios or not periodos:
        return []

    user_ids = {usuario.pk for usuario in usuarios}
    period_ids = {periodo.pk for periodo in periodos}
    desempenos = list(Desempeno.objects.filter(usuario_id__in=user_ids,periodo_id__in=period_ids,).select_related('item', 'periodo', 'usuario'))
    counts = _conteo_actividades_puntaje(user_ids, period_ids)

    performances_by_user_period = defaultdict(list)
    for desempenho in desempenos:
        performances_by_user_period[(desempenho.usuario_id, desempenho.periodo_id)].append(desempenho)

    series = []
    for periodo in periodos:
        total_avance_real = ZERO
        considerados = 0
        sobre_umbral = 0
        for usuario in usuarios:
            summary = resumen_cumplimiento(performances_by_user_period.get((usuario.pk, periodo.pk), ()),counts=counts,cap=cap)
            if not summary['items']:
                continue
            considerados += 1
            total_avance_real += summary['avance_real']
            if clasificar_umbral(summary['avance_real'],tiene_items=True,umbral=umbral,) == 'sobre':
                sobre_umbral += 1

        promedio = (total_avance_real / Decimal(considerados) if considerados else ZERO).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        porcentaje_sobre = (Decimal(sobre_umbral) * HUNDRED / Decimal(considerados) if considerados else ZERO).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        series.append({
            'periodo': periodo,
            'funcionarios_considerados': considerados,
            'promedio_avance_real': promedio,
            'porcentaje_sobre_umbral': porcentaje_sobre,
            'funcionarios_sin_items': len(usuarios) - considerados,
        })
    return series
