from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.db import transaction
from django.urls import reverse
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
from DelegadoApp.models import (
    Compromiso,
    HistorialEstadoCompromiso,
    HistorialReasignacionCompromiso,
)
from FuncionarioApp.models import Registro


def compromiso_snapshot(compromiso):
    """Return an audit-safe representation of a commitment."""
    return {
        'codigo': compromiso.codigo_publico,
        'fecha_solicitud': compromiso.fecha_solicitud.isoformat() if compromiso.fecha_solicitud else None,
        'fecha_compromiso': compromiso.fecha_compromiso.isoformat() if compromiso.fecha_compromiso else None,
        'descripcion': compromiso.descripcion,
        'solicitante_id': compromiso.solicitante_id,
        'territorio_id': compromiso.territorio_id,
        'responsable_ids': sorted(compromiso.responsable.values_list('pk', flat=True)),
        'estado': compromiso.estado,
        'observaciones': compromiso.observaciones,
        'tipo_id': compromiso.tipo_id,
        'subtipo_id': compromiso.subtipo_id,
    }


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
def actualizar_compromiso(*, compromiso, autor, nuevo_estado=None,
                          observaciones=None, responsables=None, motivo=None,
                          action='Actualizar compromiso'):
    """Update commitment fields atomically and record complete before/after values."""
    compromiso = Compromiso.objects.select_for_update().select_related(
        'agenda', 'agenda__periodo',
    ).get(pk=compromiso.pk)
    before = compromiso_snapshot(compromiso)
    responsables_anteriores = before['responsable_ids']
    responsables_nuevos = (
        sorted(user.pk if hasattr(user, 'pk') else int(user) for user in responsables)
        if responsables is not None else responsables_anteriores
    )
    responsables_cambiaron = responsables_nuevos != responsables_anteriores
    if responsables_cambiaron and not (motivo or '').strip():
        raise ValidationError({'motivo': 'El motivo de reasignación es obligatorio.'})
    previous_state = compromiso.estado
    if nuevo_estado is not None:
        compromiso.estado = nuevo_estado
    if observaciones is not None:
        compromiso.observaciones = observaciones
    compromiso.save(update_fields=['estado', 'observaciones', 'actualizado'])
    if responsables is not None:
        compromiso.responsable.set(responsables)
    after = compromiso_snapshot(compromiso)
    if before == after:
        return False
    if previous_state != compromiso.estado:
        HistorialEstadoCompromiso.objects.create(
            compromiso=compromiso,
            estado_anterior=previous_state,
            estado_nuevo=compromiso.estado,
            autor=autor,
        )
    if responsables_cambiaron:
        HistorialReasignacionCompromiso.objects.create(
            compromiso=compromiso,
            responsables_anteriores=responsables_anteriores,
            responsables_nuevos=responsables_nuevos,
            autor=autor,
            motivo=motivo.strip(),
        )
    registrar_historial(
        actor=autor,
        action=action,
        entity=f'Compromiso:{compromiso.pk}',
        before=before,
        after=after,
        period=compromiso.agenda.periodo,
    )
    return True


def actualizar_estado_compromiso(*, compromiso, autor, nuevo_estado):
    return actualizar_compromiso(
        compromiso=compromiso,
        autor=autor,
        nuevo_estado=nuevo_estado,
        action='Cambiar estado de compromiso',
    )


def marcar_compromisos_vencidos(queryset, actor):
    """Persist expired open commitments and audit each automatic transition."""
    now = timezone.now()
    candidates = queryset.filter(
        fecha_compromiso__lt=now,
    ).exclude(estado__in=(
        Compromiso.Estado.REALIZADO,
        Compromiso.Estado.CERRADO,
        Compromiso.Estado.NO_APLICA,
        Compromiso.Estado.VENCIDO,
    )).values_list('pk', flat=True)
    for commitment_id in candidates:
        commitment = Compromiso.objects.filter(pk=commitment_id).first()
        if commitment is not None:
            actualizar_compromiso(
                compromiso=commitment,
                autor=actor,
                nuevo_estado=Compromiso.Estado.VENCIDO,
                action='Vencer compromiso automáticamente',
            )


def agenda_items(*, delegation_id, period, query='', actor=None):
    """Return one normalized, deduplicated collection for the shared agenda."""
    from CoordinadorApp.models import AtencionSocial
    import unicodedata

    def normalize(value):
        value = unicodedata.normalize('NFKD', str(value or ''))
        return ''.join(char for char in value if not unicodedata.combining(char)).casefold()

    needle = normalize(query).replace('.', '').replace('-', '').replace(' ', '')
    items = []
    commitments = Compromiso.objects.filter(
        agenda__delegacion_id=delegation_id,
        agenda__periodo=period,
    ).select_related('solicitante', 'agenda').prefetch_related('responsable')
    records = Registro.objects.filter(
        autor__usuariodelegacion__delegacion_id=delegation_id,
        autor__usuariodelegacion__fecha_fin__isnull=True,
        periodo=period,
        incluir_en_agenda=True,
    ).select_related('vecino', 'autor', 'item').distinct()
    social = AtencionSocial.objects.filter(
        vecino__delegacion_id=delegation_id,
        fecha__date__range=(period.fecha_inicio, period.fecha_fin),
    ).select_related('vecino', 'gestion_atencion').order_by('-fecha')

    seen_social = set()
    for commitment in commitments:
        fields = [commitment.codigo_publico, commitment.descripcion]
        if commitment.solicitante:
            fields.extend([commitment.solicitante.rut, commitment.solicitante.nombre, commitment.solicitante.apellido])
        compact = normalize(' '.join(str(field or '') for field in fields)).replace('.', '').replace('-', '').replace(' ', '')
        if needle and needle not in normalize(' '.join(str(field or '') for field in fields)) and needle not in compact:
            continue
        can_edit = bool(actor and commitment.responsable.filter(pk=actor.pk).exists())
        items.append({'id': f'compromiso:{commitment.pk}', 'commitment_id': commitment.pk,
                      'edit_url': reverse('funcionario:compromiso_editar', args=[commitment.pk]),
                      'source': 'Compromiso', 'code': commitment.codigo_publico,
                      'date': commitment.fecha_compromiso.isoformat(), 'description': commitment.descripcion,
                      'applicant': str(commitment.solicitante or ''), 'status': commitment.get_estado_display(),
                      'editable': can_edit})
    for record in records:
        fields = [str(record.codigo), record.descripcion]
        if record.vecino:
            fields.extend([record.vecino.rut, record.vecino.nombre, record.vecino.apellido])
        compact = normalize(' '.join(str(field or '') for field in fields)).replace('.', '').replace('-', '').replace(' ', '')
        if needle and needle not in normalize(' '.join(str(field or '') for field in fields)) and needle not in compact:
            continue
        items.append({'id': f'registro:{record.pk}', 'source': 'Actividad', 'code': str(record.codigo),
                      'date': record.fecha.isoformat(), 'description': record.descripcion,
                      'applicant': str(record.vecino or ''), 'status': record.get_estado_display(),
                      'editable': False})
    for attention in social:
        if attention.gestion_atencion_id in seen_social:
            continue
        seen_social.add(attention.gestion_atencion_id)
        management = attention.gestion_atencion
        fields = [management.codigo, management.nombre]
        if attention.vecino:
            fields.extend([attention.vecino.rut, attention.vecino.nombre, attention.vecino.apellido])
        compact = normalize(' '.join(str(field or '') for field in fields)).replace('.', '').replace('-', '').replace(' ', '')
        if needle and needle not in normalize(' '.join(str(field or '') for field in fields)) and needle not in compact:
            continue
        items.append({'id': f'gestion:{management.pk}', 'source': 'Gestión social', 'code': management.codigo,
                      'date': management.fecha.isoformat(), 'description': management.nombre or 'Gestión social',
                      'applicant': str(attention.vecino or ''), 'status': 'Registrada', 'editable': False})
    return sorted(items, key=lambda item: item['date'], reverse=True)
