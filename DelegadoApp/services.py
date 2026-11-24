from decimal import Decimal, ROUND_HALF_UP

from django.db.models import OuterRef, Subquery
from django.db import transaction
from django.utils import timezone

from AdminApp.audit import registrar_historial
from AdminApp.models import Usuario
from CoordinadorApp.models import Desempeno
from CoordinadorApp.services import (
    actividades_puntuables,
    clasificar_umbral,
    consolidar_cumplimientos,
    cumplimiento_por_usuario,
    dias_habiles,
    umbral_delegacion,
)
from DelegadoApp.models import Compromiso, HistorialEstadoCompromiso
from FuncionarioApp.models import Registro


def actividad_reciente(users, period):
    """Calcula métricas derivadas de actividad sin persistir datos nuevos."""
    today = timezone.localdate()
    user_ids = [user.pk for user in users]
    period_records = Registro.objects.filter(
        autor_id__in=user_ids,
        periodo=period,
    ).exclude(estado=Registro.Estado.ANULADA).select_related('autor').order_by(
        'autor_id', '-fecha', '-creado',
    ) if period else Registro.objects.none()
    historical_records = Registro.objects.filter(
        autor_id__in=user_ids,
    ).exclude(estado=Registro.Estado.ANULADA).order_by(
        'autor_id', '-fecha', '-creado',
    )
    by_user = {user_id: [] for user_id in user_ids}
    for record in period_records:
        by_user.setdefault(record.autor_id, []).append(record)
    historical_last = {}
    for record in historical_records:
        historical_last.setdefault(record.autor_id, record)
    elapsed_days = max(
        dias_habiles(period.fecha_inicio, min(today, period.fecha_fin))
        if period else 1,
        1,
    )
    metrics = {}
    for user in users:
        records = by_user.get(user.pk, [])
        last = records[0] if records else historical_last.get(user.pk)
        days_without = (
            max((today - last.fecha).days, 0)
            if last else None
        )
        metrics[user.pk] = {
            'fecha_ultimo_registro': last.fecha if last else None,
            'ultimo_registro': last.descripcion if last else None,
            'dias_sin_ingreso': days_without,
            'promedio_diario': (
                Decimal(len(records)) / Decimal(elapsed_days)
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'sin_registros': last is None,
        }
    return metrics


def resumen_delegacion(*, delegation=None, period=None, all_delegations=False, funcionario_id=None):
    threshold = umbral_delegacion()
    empty_result = {
        'funcionarios': [],
        'below_threshold': [],
        'below_threshold_items': [],
        'threshold': threshold,
        'total_funcionarios': 0,
        'cumplimiento_colectivo': Decimal('0.00'),
        'avance_esperado_colectivo': Decimal('0.00'),
        'distribucion_semaforo': {
            state: {'count': 0, 'percentage': Decimal('0.00')}
            for state in ('verde', 'ambar', 'rojo', 'sin_items')
        },
        'cantidad_bajo_umbral': 0,
        'has_delegation': delegation is not None or all_delegations,
    }
    if delegation is None and not all_delegations:
        return empty_result

    last_description = Registro.objects.filter(
        autor_id=OuterRef('pk'),
        periodo=period,
    ).order_by('-fecha', '-creado').values('descripcion')[:1]
    last_date = Registro.objects.filter(
        autor_id=OuterRef('pk'),
        periodo=period,
    ).order_by('-fecha', '-creado').values('fecha')[:1]
    users_queryset = Usuario.objects.filter(
        is_active=True,
        usuariocargo__cargo__nombre__iexact='funcionario',
        usuariocargo__fecha_fin__isnull=True,
        usuariodelegacion__fecha_fin__isnull=True,
    )
    if delegation is not None:
        users_queryset = users_queryset.filter(
            usuariodelegacion__delegacion=delegation,
        )
    if funcionario_id:
        users_queryset = users_queryset.filter(pk=funcionario_id)
    users = list(users_queryset.distinct().annotate(
        ultimo_registro=Subquery(last_description),
        fecha_ultimo_registro=Subquery(last_date),
    ).order_by('last_name', 'first_name', 'email'))
    activity_metrics = actividad_reciente(users, period)
    performances = list(Desempeno.objects.filter(
        usuario_id__in=[user.pk for user in users],
        periodo=period,
    ).select_related('usuario', 'item', 'periodo')) if period else []
    summaries = cumplimiento_por_usuario(performances)
    rows = []
    summary_values = []
    for user in users:
        summary = summaries.get(user.pk, {
            'items': [],
            'avance_real': 0,
            'avance_esperado': 0,
        })
        summary_values.append(summary)
        rows.append({
            'usuario': user,
            'cumplimiento': summary['avance_real'],
            'esperado': summary['avance_esperado'],
            'semaforo': (
                'verde' if summary['avance_real'] >= summary['avance_esperado']
                else 'ambar'
                if summary['avance_real'] >= summary['avance_esperado'] * Decimal('0.60')
                else 'rojo'
            ),
            'umbral': threshold,
            'clasificacion_umbral': clasificar_umbral(
                summary['avance_real'],
                tiene_items=bool(summary['items']),
            ),
            'ultimo_registro': user.ultimo_registro,
            'fecha_ultimo_registro': user.fecha_ultimo_registro,
            **activity_metrics.get(user.pk, {}),
        })
    collective = consolidar_cumplimientos(
        summary_values,
        threshold=threshold,
    )
    with_items = [summary for summary in summary_values if summary['items']]
    expected_collective = (
        sum((summary['avance_esperado'] for summary in with_items), Decimal('0.00'))
        / Decimal(len(with_items))
        if with_items else Decimal('0.00')
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    below_threshold_items = [
        {
            'usuario': row['usuario'],
            'item': item['desempeno'].item,
            'cumplimiento': item['cumplimiento'],
            'esperado': item['esperado'],
        }
        for row, summary in zip(rows, summary_values)
        for item in summary['items']
        if item['cumplimiento'] < threshold
    ]
    empty_result.update({
        'funcionarios': rows,
        'below_threshold': [
            row for row in rows
            if row['clasificacion_umbral'] is not None
            and row['cumplimiento'] < threshold
        ],
        'below_threshold_items': below_threshold_items,
        **collective,
        'avance_esperado_colectivo': expected_collective,
    })
    return empty_result


def detalle_actividades(*, user_ids, period):
    """Lista las actividades exactas que alimentan el cumplimiento."""
    records = actividades_puntuables(user_ids, [period.pk] if period else [])
    return [
        {
            'registro': record,
            'puntaje_aportado': Decimal('1.00'),
        }
        for record in records
    ]


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
