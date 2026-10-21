from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from config.decorators import cargo_required
from CoordinadorApp.forms import PeriodoForm
from CoordinadorApp.models import Desempeno, Periodo
from DelegadoApp.models import Agenda
from FuncionarioApp.models import Registro


def _period_snapshot(periodo):
    return {
        'nombre': periodo.nombre,
        'fecha_inicio': periodo.fecha_inicio.isoformat(),
        'fecha_fin': periodo.fecha_fin.isoformat(),
        'estado': periodo.estado,
    }


def _has_associated_records(periodo):
    return (
        periodo.desempenos.exists()
        or periodo.registros.exists()
        or periodo.agendas.exists()
    )


@cargo_required('coordinador', 'admin', 'administrador')
def home(request):
    cargo_name = request.user.cargo.nombre.strip().casefold()
    is_coordinator = cargo_name == 'coordinador'
    can_reopen = cargo_name in {'coordinador', 'admin', 'administrador'}

    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        periodo_id = request.POST.get('periodo_id')
        if action in {'cerrar', 'reabrir', 'eliminar'}:
            periodo = get_object_or_404(Periodo, pk=periodo_id)
            before = _period_snapshot(periodo)

            if action == 'reabrir':
                if not can_reopen:
                    messages.error(request, 'No tienes autorización para reabrir períodos.')
                elif periodo.estado == Periodo.Estado.ABIERTO:
                    messages.info(request, 'El período ya está abierto.')
                else:
                    with transaction.atomic():
                        periodo.estado = Periodo.Estado.ABIERTO
                        periodo.save(update_fields=['estado'])
                        registrar_historial(
                            actor=request.user,
                            action='Reabrir período',
                            entity=f'Periodo:{periodo.pk}',
                            before=before,
                            after=_period_snapshot(periodo),
                            period=periodo,
                        )
                    messages.success(request, 'El período se reabrió correctamente.')
            elif action == 'cerrar':
                if not is_coordinator:
                    messages.error(request, 'Solo Coordinación puede cerrar períodos.')
                elif periodo.estado == Periodo.Estado.CERRADO:
                    messages.info(request, 'El período ya está cerrado.')
                else:
                    with transaction.atomic():
                        periodo.estado = Periodo.Estado.CERRADO
                        periodo.save(update_fields=['estado'])
                        registrar_historial(
                            actor=request.user,
                            action='Cerrar período',
                            entity=f'Periodo:{periodo.pk}',
                            before=before,
                            after=_period_snapshot(periodo),
                            period=periodo,
                        )
                    messages.success(request, 'El período se cerró correctamente.')
            elif periodo.estado == Periodo.Estado.CERRADO:
                messages.error(request, 'Un período cerrado no se puede eliminar; primero debe reabrirse.')
            elif _has_associated_records(periodo):
                messages.error(request, 'Este período tiene información asociada. Ciérralo en lugar de eliminarlo.')
            elif not is_coordinator:
                messages.error(request, 'Solo Coordinación puede eliminar períodos.')
            else:
                entity = f'Periodo:{periodo.pk}'
                with transaction.atomic():
                    registrar_historial(
                        actor=request.user,
                        action='Eliminar período',
                        entity=entity,
                        before=before,
                    )
                    periodo.delete()
                messages.success(request, 'El período se eliminó correctamente.')
            return redirect('coordinador:home')

        instance = get_object_or_404(Periodo, pk=periodo_id) if periodo_id else None
        if not is_coordinator:
            messages.error(request, 'Solo Coordinación puede crear o editar períodos.')
            return redirect('coordinador:home')
        if instance and instance.estado == Periodo.Estado.CERRADO:
            messages.error(request, 'Un período cerrado es de solo lectura. Reábrelo para editarlo.')
            return redirect('coordinador:home')

        before = _period_snapshot(instance) if instance else None
        form = PeriodoForm(request.POST, instance=instance)
        if form.is_valid():
            with transaction.atomic():
                periodo = form.save()
                registrar_historial(
                    actor=request.user,
                    action='Editar período' if before else 'Crear período',
                    entity=f'Periodo:{periodo.pk}',
                    before=before,
                    after=_period_snapshot(periodo),
                    period=periodo,
                )
            messages.success(
                request,
                'El período se actualizó correctamente.' if instance
                else 'El período quedó configurado.',
            )
            return redirect('coordinador:home')
        messages.error(request, 'No se pudo guardar el período. Revisa las fechas y los campos.')
    else:
        edit_id = request.GET.get('editar')
        instance = get_object_or_404(Periodo, pk=edit_id) if edit_id else None
        if instance and instance.estado == Periodo.Estado.CERRADO:
            messages.error(request, 'Un período cerrado es de solo lectura. Reábrelo para editarlo.')
            return redirect('coordinador:home')
        if not is_coordinator:
            instance = None
        form = PeriodoForm(instance=instance)

    periodos = Periodo.objects.annotate(
        tiene_datos=(
            Exists(Desempeno.objects.filter(periodo_id=OuterRef('pk')))
            | Exists(Registro.objects.filter(periodo_id=OuterRef('pk')))
            | Exists(Agenda.objects.filter(periodo_id=OuterRef('pk')))
        ),
    )
    return render(request, 'CoordinadorApp/index.html', {
        'sgr_role': 'Coordinación', 'form': form, 'periodos': periodos,
        'editing_period': instance if is_coordinator else None,
        'can_manage_periods': is_coordinator,
        'can_reopen_periods': can_reopen,
        'sidebar_modules': (
            'Metas e indicadores', 'Avance esperado', 'Informes de gestión',
            'Tendencias históricas', 'Actividades', 'Gestión de periodos',
        ),
        'periodo_count': periodos.count(), 'periodos_abiertos': periodos.filter(estado=Periodo.Estado.ABIERTO).count(),
        'desempeno_count': Desempeno.objects.count(),
    })
