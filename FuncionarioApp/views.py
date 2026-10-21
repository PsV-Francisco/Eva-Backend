from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from AdminApp.audit import registrar_historial
from AdminApp.models import ParametroSistema
from config.decorators import cargo_required
from CoordinadorApp.models import Desempeno, Periodo
from CoordinadorApp.services import resumen_cumplimiento
from DelegadoApp.models import Agenda, Compromiso
from DelegadoApp.forms import CompromisoEstadoForm
from DelegadoApp.services import actualizar_estado_compromiso
from FuncionarioApp.forms import CasoSocialForm, GestionAtencionForm, RegistroForm
from FuncionarioApp.models import AtencionSocial, CasoSocial, GestionAtencion, Registro
from SupervisorApp.models import Evidencia


def _registro_snapshot(registro):
    return {
        'codigo': str(registro.codigo),
        'fecha': registro.fecha.isoformat(),
        'item_id': registro.item_id,
        'periodo_id': registro.periodo_id,
        'descripcion': registro.descripcion,
        'estado': registro.estado,
    }


@cargo_required('funcionario')
def home(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'guardar')
        registro_id = request.POST.get('registro_id')
        if registro_id:
            registro = get_object_or_404(
                Registro, pk=registro_id, autor=request.user,
                estado=Registro.Estado.PENDIENTE,
                periodo__estado=Periodo.Estado.ABIERTO,
            )
            if action == 'eliminar' and registro.evidencias_registros.exists():
                messages.error(request, 'No se puede eliminar una actividad que ya tiene evidencias asociadas.')
                return redirect('funcionario:home')
            period = registro.periodo
        else:
            registro = None
            period = None

        if action == 'eliminar':
            if registro is None:
                messages.error(request, 'No se encontró la actividad que intentas eliminar.')
            else:
                before = _registro_snapshot(registro)
                entity = f'Registro:{registro.pk}'
                with transaction.atomic():
                    registro.delete()
                    registrar_historial(
                        actor=request.user,
                        action='Eliminar actividad',
                        entity=entity,
                        before=before,
                        period=period,
                    )
                messages.success(request, 'La actividad se eliminó correctamente.')
            return redirect('funcionario:home')

        before = _registro_snapshot(registro) if registro else None
        form = RegistroForm(
            request.POST, request.FILES or None, instance=registro, user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                registro = form.save(commit=False)
                registro.autor = request.user
                registro.save()
                uploaded_file = form.cleaned_data.get('evidencia')
                if uploaded_file:
                    Evidencia.objects.create(archivo=uploaded_file, registro=registro)
                registrar_historial(
                    actor=request.user,
                    action='Editar actividad' if before else 'Crear actividad',
                    entity=f'Registro:{registro.pk}',
                    before=before,
                    after=_registro_snapshot(registro),
                    period=registro.periodo,
                )
            messages.success(
                request,
                f'Actividad actualizada: {registro.codigo}' if registro_id
                else f'Actividad registrada con código {registro.codigo}.',
            )
            return redirect('funcionario:home')
        messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    else:
        edit_id = request.GET.get('editar')
        registro = get_object_or_404(
            Registro, pk=edit_id, autor=request.user,
            estado=Registro.Estado.PENDIENTE,
            periodo__estado=Periodo.Estado.ABIERTO,
        ) if edit_id else None
        form = RegistroForm(instance=registro, user=request.user)

    registros = Registro.objects.filter(autor=request.user).select_related('item', 'periodo')
    return render(request, 'FuncionarioApp/index.html', {
        'sgr_role': 'Funcionario', 'form': form, 'registros': registros[:20],
        'editing_record': registro,
        'sidebar_modules': (
            {'label': 'Registro de Actividades', 'url_name': 'funcionario:home'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Agenda colectiva', 'url_name': 'funcionario:agenda_colectiva'},
            {'label': 'Cumplimiento', 'url_name': 'funcionario:cumplimiento'},
        ),
        'registro_count': registros.count(),
    })


@cargo_required('funcionario')
def cumplimiento(request):
    assigned_periods = Periodo.objects.filter(
        desempenos__usuario=request.user,
    ).distinct().order_by('-fecha_inicio')
    period_id = request.GET.get('periodo')
    period = (
        assigned_periods.filter(pk=int(period_id)).first()
        if period_id and period_id.isdecimal()
        else None
    )
    if period is None:
        period = assigned_periods.first()
    performances = Desempeno.objects.filter(
        usuario=request.user,
        periodo=period,
    ).select_related('item', 'periodo') if period else Desempeno.objects.none()
    summary = resumen_cumplimiento(performances)
    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Registro de Actividades', 'url_name': 'funcionario:home'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Agenda colectiva', 'url_name': 'funcionario:agenda_colectiva'},
            {'label': 'Cumplimiento', 'url_name': 'funcionario:cumplimiento'},
        ),
        'periodos': assigned_periods,
        'periodo_seleccionado': period,
        'summary': summary,
        'item_count': len(summary['items']),
    })


@cargo_required('funcionario')
def atencion_social(request):
    case_form = CasoSocialForm()
    attention_form = GestionAtencionForm()
    selected_case = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'crear_caso':
            case_form = CasoSocialForm(request.POST)
            if case_form.is_valid():
                with transaction.atomic():
                    case_record = case_form.save(commit=False)
                    case_record.usuario = request.user
                    case_record.save()
                    case = CasoSocial.objects.create(atencion_social=case_record)
                    registrar_historial(
                        actor=request.user,
                        action='Crear caso social',
                        entity=f'CasoSocial:{case.pk}',
                        after={
                            'codigo': str(case.codigo),
                            'usuario_id': request.user.pk,
                            'tipo_atencion': case_record.tipo_atencion,
                        },
                    )
                messages.success(request, f'Caso social creado: {case.codigo}.')
                return redirect('funcionario:atencion_social')
            messages.error(request, 'Revisa los datos del caso social.')
        elif action == 'agregar_atencion':
            case = get_object_or_404(
                CasoSocial.objects.select_related('atencion_social'),
                pk=request.POST.get('caso_id'),
                atencion_social__usuario=request.user,
            )
            selected_case = case
            attention_form = GestionAtencionForm(request.POST, request.FILES)
            if attention_form.is_valid():
                with transaction.atomic():
                    locked_case = CasoSocial.objects.select_for_update().select_related(
                        'atencion_social',
                    ).get(pk=case.pk)
                    atenciones = GestionAtencion.objects.filter(
                        atencion=locked_case.atencion_social,
                    )
                    next_number = atenciones.count() + 1
                    if next_number > 3:
                        messages.error(request, 'Este caso ya alcanzó el máximo de 3 atenciones.')
                    else:
                        attention = attention_form.save(commit=False)
                        attention.atencion = locked_case.atencion_social
                        attention.numero_gestion = next_number
                        attention.save()
                        evidence = Evidencia.objects.create(
                            archivo=attention_form.cleaned_data['evidencia'],
                            gestion_atencion=attention,
                        )
                        registrar_historial(
                            actor=request.user,
                            action='Crear atención social',
                            entity=f'GestionAtencion:{attention.pk}',
                            after={
                                'codigo': str(attention.codigo),
                                'caso_codigo': str(locked_case.codigo),
                                'numero': attention.numero_gestion,
                                'evidencia_codigo': str(evidence.codigo),
                            },
                        )
                        messages.success(
                            request,
                            f'Atención registrada con código {attention.codigo}.',
                        )
                        return redirect('funcionario:atencion_social')
            else:
                messages.error(request, 'Revisa la fecha, observación y evidencia adjunta.')
        else:
            messages.error(request, 'La acción solicitada no es válida.')

    cases = CasoSocial.objects.filter(
        atencion_social__usuario=request.user,
    ).select_related('atencion_social').prefetch_related(
        'atencion_social__gestiones__evidencias',
    )
    return render(request, 'FuncionarioApp/atencion_social.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Registro de Actividades', 'url_name': 'funcionario:home'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Agenda colectiva', 'url_name': 'funcionario:agenda_colectiva'},
            {'label': 'Cumplimiento', 'url_name': 'funcionario:cumplimiento'},
        ),
        'case_form': case_form,
        'attention_form': attention_form,
        'cases': cases,
        'case_count': cases.count(),
        'selected_case': selected_case,
    })


@cargo_required('funcionario')
def agenda_colectiva(request):
    if request.method == 'POST' and request.POST.get('action') == 'estado_compromiso':
        if not request.user.delegacion_id:
            messages.error(request, 'Tu cuenta no tiene una delegación asignada.')
            return redirect('funcionario:agenda_colectiva')
        commitment = get_object_or_404(
            Compromiso.objects.select_related('agenda', 'agenda__periodo').filter(
                agenda__delegacion_id=request.user.delegacion_id,
                responsables=request.user,
            ),
            pk=request.POST.get('compromiso_id'),
        )
        if commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
            messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
        else:
            state_form = CompromisoEstadoForm(request.POST)
            if state_form.is_valid():
                if actualizar_estado_compromiso(
                    compromiso=commitment,
                    autor=request.user,
                    nuevo_estado=state_form.cleaned_data['estado'],
                ):
                    messages.success(request, 'El estado y su historial quedaron actualizados.')
                else:
                    messages.info(request, 'El compromiso ya tenía ese estado.')
            else:
                messages.error(request, 'Selecciona un estado válido.')
        period_id = request.POST.get('periodo')
        destination = redirect('funcionario:agenda_colectiva')
        if period_id and period_id.isdecimal():
            destination['Location'] += f'?periodo={int(period_id)}'
        return destination

    periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO).order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    selected_period = (
        periods.filter(pk=int(period_id)).first()
        if period_id.isdecimal()
        else None
    )
    if selected_period is None:
        selected_period = periods.first()
    registros = Registro.objects.none()
    commitments = Compromiso.objects.none()
    if request.user.delegacion_id and selected_period:
        registros = Registro.objects.filter(
            autor__delegacion_id=request.user.delegacion_id,
            periodo=selected_period,
            incluir_en_agenda=True,
        ).select_related('autor', 'item').order_by('-fecha')
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=request.user.delegacion_id,
            agenda__periodo=selected_period,
        ).select_related('agenda', 'agenda__periodo').prefetch_related('responsables')
    return render(request, 'FuncionarioApp/agenda_colectiva.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Registro de actividades', 'url_name': 'funcionario:home'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Agenda colectiva', 'url_name': 'funcionario:agenda_colectiva'},
            {'label': 'Cumplimiento', 'url_name': 'funcionario:cumplimiento'},
        ),
        'periodos': periods,
        'periodo_seleccionado': selected_period,
        'registros': registros,
        'compromisos': commitments,
        'delegation_assigned': bool(request.user.delegacion_id),
    })
