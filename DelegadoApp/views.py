from django.contrib import messages
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from decimal import Decimal

from AdminApp.audit import registrar_historial
from AdminApp.models import ParametroSistema, Usuario
from config.decorators import cargo_required
from config.delegations import active_delegation
from CoordinadorApp.models import Desempeno, Periodo
from CoordinadorApp.services import cumplimiento_por_usuario
from DelegadoApp.forms import CompromisoEstadoForm, CompromisoForm
from DelegadoApp.models import Agenda, Compromiso, HistorialEstadoCompromiso
from DelegadoApp.services import actualizar_estado_compromiso
from FuncionarioApp.models import Registro


@cargo_required('delegado')
def home(request):
    delegation = active_delegation(request)
    delegation_id = delegation.pk if delegation else None
    commitments = Compromiso.objects.none()
    if delegation_id:
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
        ).select_related('agenda', 'agenda__periodo').prefetch_related(
            'responsables', 'evidencias_compromiso',
        )

    if request.method == 'POST' and request.POST.get('action') == 'estado':
        if not delegation_id:
            messages.error(request, 'Tu cuenta no tiene una delegación asignada.')
        else:
            compromiso = get_object_or_404(commitments, pk=request.POST.get('compromiso_id'))
            if compromiso.agenda.periodo.estado != Periodo.Estado.ABIERTO:
                messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            else:
                state_form = CompromisoEstadoForm(request.POST)
                if state_form.is_valid():
                    new_state = state_form.cleaned_data['estado']
                    if actualizar_estado_compromiso(
                        compromiso=compromiso,
                        autor=request.user,
                        nuevo_estado=new_state,
                    ):
                        messages.success(request, 'El estado y su historial quedaron actualizados.')
                    else:
                        messages.info(request, 'El compromiso ya tenía ese estado.')
                else:
                    messages.error(request, 'Selecciona un estado válido.')
        return redirect('delegado:home')

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        compromiso_id = request.POST.get('compromiso_id')
        if compromiso_id:
            commitment = get_object_or_404(commitments, pk=compromiso_id)
        else:
            commitment = None

        if action == 'eliminar':
            if commitment is None:
                messages.error(request, 'No se encontró el compromiso que intentas eliminar.')
            elif commitment.evidencias_compromiso.exists():
                messages.error(request, 'No se puede eliminar un compromiso con evidencias asociadas.')
            elif commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
                messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            else:
                try:
                    before = {
                        'descripcion': commitment.descripcion,
                        'fecha': commitment.fecha.isoformat(),
                        'estado': commitment.estado,
                        'observaciones': commitment.observaciones,
                    }
                    entity = f'Compromiso:{commitment.pk}'
                    period = commitment.agenda.periodo
                    with transaction.atomic():
                        commitment.delete()
                        registrar_historial(
                            actor=request.user,
                            action='Eliminar compromiso',
                            entity=entity,
                            before=before,
                            period=period,
                        )
                    messages.success(request, 'El compromiso se eliminó correctamente.')
                except ProtectedError:
                    messages.error(request, 'No se puede eliminar un compromiso que tiene información asociada.')
            return redirect('delegado:home')

        if commitment and commitment.evidencias_compromiso.exists():
            messages.error(request, 'No se puede modificar un compromiso con evidencias asociadas.')
            return redirect('delegado:home')
        if commitment and commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
            messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
            return redirect('delegado:home')

        if not delegation_id:
            messages.error(request, 'Asigna una delegación a tu cuenta antes de crear compromisos.')
            return redirect('delegado:home')

        form = CompromisoForm(
            request.POST, user=request.user, delegation=delegation,
            instance=commitment,
        )
        if form.is_valid():
            period = form.cleaned_data['periodo']
            agenda, _ = Agenda.objects.get_or_create(
                delegacion_id=delegation_id, periodo=period,
            )
            before = None
            if commitment:
                before = {
                    'descripcion': commitment.descripcion,
                    'fecha': commitment.fecha.isoformat(),
                    'estado': commitment.estado,
                    'observaciones': commitment.observaciones,
                }
            previous_state = commitment.estado if commitment else ''
            commitment = form.save(commit=False)
            commitment.agenda = agenda
            with transaction.atomic():
                commitment.save()
                form.save_m2m()
                new_snapshot = {
                    'descripcion': commitment.descripcion,
                    'fecha': commitment.fecha.isoformat(),
                    'estado': commitment.estado,
                    'observaciones': commitment.observaciones,
                }
                if previous_state != commitment.estado:
                    HistorialEstadoCompromiso.objects.create(
                        compromiso=commitment,
                        estado_anterior=previous_state,
                        estado_nuevo=commitment.estado,
                        autor=request.user,
                    )
                registrar_historial(
                    actor=request.user,
                    action='Editar compromiso' if before else 'Crear compromiso',
                    entity=f'Compromiso:{commitment.pk}',
                    before=before,
                    after=new_snapshot,
                    period=period,
                )
            messages.success(
                request,
                'El compromiso se actualizó correctamente.' if compromiso_id
                else 'El compromiso quedó agregado a la agenda.',
            )
            return redirect('delegado:home')
        else:
            messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    else:
        edit_id = request.GET.get('editar')
        commitment = get_object_or_404(commitments, pk=edit_id) if edit_id else None
        form = CompromisoForm(
            instance=commitment, user=request.user, delegation=delegation,
        )

    return render(request, 'DelegadoApp/index.html', {
        'sgr_role': 'Delegación', 'form': form, 'commitments': commitments[:30],
        'commitment_count': commitments.count(), 'has_delegation': bool(delegation_id),
        'editing_commitment': commitment,
        'sidebar_modules': (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
        ),
    })


@cargo_required('delegado')
def resumen(request):
    delegation = active_delegation(request)
    delegation_id = delegation.pk if delegation else None
    period_id = request.GET.get('periodo', '')
    selected_period = (
        Periodo.objects.filter(pk=int(period_id)).first()
        if period_id.isdecimal()
        else Periodo.objects.filter(
            estado=Periodo.Estado.ABIERTO,
        ).order_by('-fecha_inicio').first()
    )
    periods = Periodo.objects.order_by('-fecha_inicio')
    if not delegation_id:
        return render(request, 'DelegadoApp/resumen.html', {
            'sgr_role': 'Delegación',
            'sidebar_modules': (
                {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
                {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
            ),
            'periodos': periods,
            'periodo_seleccionado': selected_period,
            'funcionarios': [],
            'below_threshold': [],
            'threshold': ParametroSistema.obtener(
                ParametroSistema.Clave.UMBRAL_DELEGACION,
            ),
            'has_delegation': False,
        })

    last_description = Registro.objects.filter(
        autor_id=OuterRef('pk'),
        periodo=selected_period,
    ).order_by('-fecha', '-creado').values('descripcion')[:1]
    last_date = Registro.objects.filter(
        autor_id=OuterRef('pk'),
        periodo=selected_period,
    ).order_by('-fecha', '-creado').values('fecha')[:1]
    users = list(Usuario.objects.filter(
        Q(delegacion_id=delegation_id)
        | Q(delegaciones_autorizadas__pk=delegation_id),
        is_active=True,
        cargo__nombre__iexact='funcionario',
    ).distinct().annotate(
        ultimo_registro=Subquery(last_description),
        fecha_ultimo_registro=Subquery(last_date),
    ).order_by('last_name', 'first_name', 'email'))
    performances = list(Desempeno.objects.filter(
        usuario_id__in=[user.pk for user in users],
        periodo=selected_period,
    ).select_related('usuario', 'item', 'periodo')) if selected_period else []
    summaries = cumplimiento_por_usuario(performances)
    threshold = ParametroSistema.obtener(ParametroSistema.Clave.UMBRAL_DELEGACION)
    rows = []
    for user in users:
        summary = summaries.get(user.pk, {
            'items': [],
            'avance_real': 0,
            'avance_esperado': 0,
            'total_avance': 0,
            'total_meta': 0,
            'total_aporte': 0,
        })
        rows.append({
            'usuario': user,
            'cumplimiento': summary['avance_real'],
            'esperado': summary['avance_esperado'],
            'semaforo': (
                'verde' if summary['avance_real'] >= summary['avance_esperado']
                else 'ambar' if summary['avance_real'] >= summary['avance_esperado'] * Decimal('0.60')
                else 'rojo'
            ),
            'ultimo_registro': user.ultimo_registro,
            'fecha_ultimo_registro': user.fecha_ultimo_registro,
        })
    return render(request, 'DelegadoApp/resumen.html', {
        'sgr_role': 'Delegación',
        'sidebar_modules': (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
        ),
        'periodos': periods,
        'periodo_seleccionado': selected_period,
        'funcionarios': rows,
        'below_threshold': [
            row for row in rows if row['cumplimiento'] < threshold
        ],
        'threshold': threshold,
        'has_delegation': True,
    })
