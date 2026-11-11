# Importaciones de Django y estándar
from decimal import Decimal
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
import json

# Importaciones de la aplicación AdminApp
from AdminApp.audit import registrar_historial
from AdminApp.delegation_scope import (available_delegations,filter_by_delegation,)
from AdminApp.models import Delegacion

# Importaciones de la aplicación FuncionarioApp
from FuncionarioApp.models import (Beneficiado,CargoJv,JuntaVecino,Registro,Subtipo,Territorio,Tipo,Vecino,normalizar_telefono,)
from django.db.models import Count

# Importaciones de la aplicación CoordinadorApp
from CoordinadorApp.models import AtencionSocial, Desempeno, GestionAtencion, Periodo
from CoordinadorApp.services import clasificar_umbral, resumen_cumplimiento, umbral_delegacion

# Importaciones de la aplicación DelegadoApp y SupervisorApp
from DelegadoApp.models import Agenda, Compromiso
from DelegadoApp.services import actualizar_estado_compromiso
from DelegadoApp.forms import CompromisoEstadoForm
from SupervisorApp.models import Evidencia

# Importaciones de Decoradores y Formularios de FuncionarioApp
from config.decorators import cargo_required
from config.delegations import active_delegation
from FuncionarioApp.forms import (AtencionSocialForm,CompromisoEvidenciaForm,FuncionarioCompromisoForm,JuntaVecinoForm,RegistroForm,VecinoForm,GestionAtencionForm)


@cargo_required('funcionario', permission='access_employee_dashboard')
def home(request):
    """Vista del tablero principal del funcionario."""
    return _render_cumplimiento(request)

def _es_encargado_social(user):
    """Detecta si el usuario posee un rol o cargo de Encargado Social."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    nombres_validos = {
        'encargado social',
        'encargado área social',
        'encargado area social',
        'social',
    }

    # 1. Verificación por relación directa o atributo 'roles'
    if hasattr(user, 'roles'):
        try:
            roles_obj = user.roles
            if hasattr(roles_obj, 'filter'):
                if roles_obj.filter(nombre__iregex=r'^encargado (área |area )?social$').exists():
                    return True
            elif hasattr(roles_obj, 'all'):
                if any(getattr(r, 'nombre', '').strip().casefold() in nombres_validos for r in roles_obj.all()):
                    return True
            elif isinstance(roles_obj, (list, tuple, set)):
                if any(getattr(r, 'nombre', '').strip().casefold() in nombres_validos for r in roles_obj):
                    return True
        except Exception:
            pass

    # 2. Verificación por modelo intermedio UsuarioRol
    if hasattr(user, 'usuariorol_set'):
        try:
            if user.usuariorol_set.filter(rol__nombre__iregex=r'^encargado (área |area )?social$').exists():
                return True
        except Exception:
            pass

    # 3. Verificación por cargo directo o UsuarioCargo
    cargo = getattr(user, 'cargo', None)
    if cargo and getattr(cargo, 'nombre', '').strip().casefold() in nombres_validos:
        return True

    return False

def _funcionario_sidebar_modules():
    """Retorna los módulos navegables del menú lateral."""
    return (
        {'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
        {'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
        {'label': 'Gestión Junta de Vecinos', 'url_name': 'funcionario:juntas'},
        {'label': 'Gestión de Atenciones Sociales', 'url_name': 'funcionario:atencion_social'},
        {'label': 'Gestión de Casos Sociales', 'url_name': 'funcionario:casos_sociales'},
        {'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
        {'label': 'Agenda Colectiva', 'url_name': 'funcionario:agenda_colectiva'},
    )

def _telefono_repetido(vecino):
    phone = normalizar_telefono(vecino.telefono)
    if not phone:
        return False
    return any(
        normalizar_telefono(value) == phone
        for value in Vecino.objects.filter(
            delegacion_id=vecino.delegacion_id,
        ).exclude(pk=vecino.pk).values_list('telefono', flat=True)
    )



#Funciones del Tablero Personal
def _render_cumplimiento(request):
    # 1. Obtener todos los períodos ordenados cronológicamente
    assigned_periods = Periodo.objects.all().order_by('-fecha_inicio')
    
    # 2. Período para los CUADROS SUPERIORES (Último desempeño registrado del funcionario)
    last_performance_period = Periodo.objects.filter(
        desempenos__usuario=request.user
    ).order_by('-fecha_inicio').first()
    
    # Si no tiene desempeño registrado en ningún período, usamos el primer período disponible
    top_period = last_performance_period or assigned_periods.first()
    
    top_performances = Desempeno.objects.filter(
        usuario=request.user,
        periodo=top_period,
    ).select_related('item', 'periodo') if top_period else Desempeno.objects.none()

    # Obtener conteo real de actividades/registros por ítem para el período superior
    top_counts = {}
    if top_period and top_performances.exists():
        # Consultar conteos de la tabla Registro
        registro_counts = Registro.objects.filter(
            autor=request.user,
            periodo=top_period
        ).values('item_id').annotate(total=Count('id'))
        
        counts_dict = {r['item_id']: Decimal(r['total']) for r in registro_counts}
        
        for row in top_performances:
            # Usar recuento real de registros si existe; de lo contrario, usar row.avance
            avance_val = counts_dict.get(row.item_id, Decimal(row.avance or 0))
            top_counts[(row.usuario_id, row.item_id, row.periodo_id)] = avance_val
    
    summary_top = resumen_cumplimiento(top_performances, counts=top_counts)

    # 3. Período para el SEGUNDO BLOQUE (Detalle por Ítem - Filtro Dinámico)
    period_id = request.GET.get('periodo', '').strip()
    selected_period = None

    if period_id and period_id.isdigit():
        selected_period = assigned_periods.filter(pk=int(period_id)).first()
        
    if selected_period is None:
        selected_period = top_period

    detail_performances = Desempeno.objects.filter(
        usuario=request.user,
        periodo=selected_period,
    ).select_related('item', 'periodo') if selected_period else Desempeno.objects.none()

    # Obtener conteo real de actividades/registros por ítem para el período seleccionado
    detail_counts = {}
    if selected_period and detail_performances.exists():
        registro_counts_detail = Registro.objects.filter(
            autor=request.user,
            periodo=selected_period
        ).values('item_id').annotate(total=Count('id'))
        
        counts_detail_dict = {r['item_id']: Decimal(r['total']) for r in registro_counts_detail}
        
        for row in detail_performances:
            avance_val = counts_detail_dict.get(row.item_id, Decimal(row.avance or 0))
            detail_counts[(row.usuario_id, row.item_id, row.periodo_id)] = avance_val

    summary_detail = resumen_cumplimiento(detail_performances, counts=detail_counts)
    es_encargado_social = _es_encargado_social(request.user)

    # 4. Renderizado a la plantilla
    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'periodos': assigned_periods,
        'periodo_seleccionado': selected_period,
        # Cuadros superiores
        'summary': summary_top,
        # Resumen y detalle específico del período seleccionado
        'summary_detail': summary_detail,
        'item_count': len(summary_detail['items']),
        'es_encargado_social': es_encargado_social,
        'umbral_delegacion': umbral_delegacion(),
        'clasificacion_umbral': clasificar_umbral(
            summary_top['avance_real'],
            tiene_items=bool(summary_top['items']),
        ),
    })

@cargo_required('funcionario', permission='manage_employee_compliance')
def cumplimiento(request):
    return redirect('funcionario:home')



# Funciones de Registro
def _registro_snapshot(registro):
    """Genera una representación en diccionario de una actividad registrada para auditoría e historial."""
    return {
        'codigo': str(registro.codigo),
        'fecha': registro.fecha.isoformat(),
        'item_id': registro.item_id,
        'periodo_id': registro.periodo_id,
        'tipo_id': registro.tipo_id,
        'subtipo_id': registro.subtipo_id,
        'descripcion': registro.descripcion,
        'estado': registro.estado,
    }

@cargo_required('funcionario', permission='manage_employee_activities')
def gestion_actividades(request):
    registration_id = request.POST.get('registro_id') if request.method == 'POST' else None
    if request.method != 'POST':
        registration_id = request.GET.get('editar')
    registro = None
    if registration_id:
        registro = get_object_or_404(
            Registro.objects.select_related('periodo'),
            pk=registration_id,
            autor=request.user,
            estado=Registro.Estado.PENDIENTE,
            periodo__estado=Periodo.Estado.ABIERTO,
        )

    if request.method == 'POST' and request.POST.get('action') == 'eliminar':
        if registro.evidencias_registros.exists():
            messages.error(
                request,
                'No se puede eliminar una actividad que ya tiene evidencias asociadas.',
            )
        else:
            before = _registro_snapshot(registro)
            period = registro.periodo
            with transaction.atomic():
                registro.delete()
                registrar_historial(
                    actor=request.user,
                    action='Eliminar actividad',
                    entity=f'Registro:{registro.pk}',
                    before=before,
                    period=period,
                )
            messages.success(request, 'La actividad se eliminó correctamente.')
        return redirect('funcionario:gestion_actividades')

    form = RegistroForm(
        request.POST or None,
        request.FILES or None,
        instance=registro,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        before = _registro_snapshot(registro) if registro else None
        with transaction.atomic():
            registro = form.save(commit=False)
            registro.autor = request.user
            registro.save()
            uploaded_file = form.cleaned_data.get('evidencia')
            if uploaded_file:
                Evidencia.objects.create(
                    archivo=uploaded_file,
                    registro=registro,
                    autor=request.user,
                )
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
            f'Actividad actualizada: {registro.codigo}' if before
            else f'Actividad registrada con código {registro.codigo}.',
        )
        return redirect('funcionario:gestion_actividades')
    if request.method == 'POST':
        messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')

    registros = Registro.objects.filter(autor=request.user).select_related(
        'item', 'periodo', 'tipo', 'subtipo',
    )

    return render(request, 'FuncionarioApp/index.html', {
        'sgr_role': 'Funcionario',
        'form': form,
        'registros': registros[:20],
        'editing_record': registro,
        'sidebar_modules': _funcionario_sidebar_modules(),
        'registro_count': registros.count(),
    })

@require_GET
def subtipos_por_tipo(request, tipo_id):
    subtipos = list(
        Subtipo.objects.filter(tipo_id=tipo_id, estado=Subtipo.Estado.ACTIVADO)
        .order_by('nombre')
        .values('pk', 'nombre')
    )
    return JsonResponse({'subtipos': subtipos})

@cargo_required('funcionario', permission='view_employee_record_detail')
@require_GET
def detalle_registro_json(request, registro_id):
    registro = get_object_or_404(Registro, pk=registro_id, autor=request.user)
    subtipos = list(
        Subtipo.objects.filter(tipo_id=registro.tipo_id, estado=Subtipo.Estado.ACTIVADO)
        .order_by('nombre')
        .values('pk', 'nombre')
    )
    return JsonResponse({
        'id': registro.pk,
        'codigo': str(registro.codigo),
        'fecha': registro.fecha.strftime('%Y-%m-%d'),
        'descripcion': registro.descripcion,
        'contacto': registro.contacto or '',
        'telefono': registro.telefono or '',
        'accion': registro.accion or '',
        'estado': registro.estado,
        'incluir_en_agenda': registro.incluir_en_agenda,
        'item_id': registro.item_id,
        'periodo_id': registro.periodo_id,
        'tipo_id': registro.tipo_id,
        'subtipo_id': registro.subtipo_id,
        'evidencia_url': registro.evidencia.archivo.url if registro.evidencia and registro.evidencia.archivo else None,
        'subtipos_disponibles': subtipos,
    })


@cargo_required('funcionario', permission='edit_employee_record_ajax')
@require_POST
def editar_registro_ajax(request, registro_id):
    registro = get_object_or_404(Registro, pk=registro_id, autor=request.user)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    fecha = data.get('fecha')
    descripcion = data.get('descripcion', '').strip()
    contacto = data.get('contacto', '').strip()
    telefono = data.get('telefono') or None
    accion = data.get('accion', '').strip()
    incluir_en_agenda = bool(data.get('incluir_en_agenda', False))
    item_id = data.get('item_id')
    periodo_id = data.get('periodo_id')
    tipo_id = data.get('tipo_id')
    subtipo_id = data.get('subtipo_id')

    if not fecha or not descripcion or not item_id or not periodo_id or not tipo_id or not subtipo_id:
        return JsonResponse({'success': False, 'message': 'Por favor completa todos los campos requeridos (*).'}, status=400)

    before = _registro_snapshot(registro)
    try:
        with transaction.atomic():
            registro.fecha = fecha
            registro.descripcion = descripcion
            registro.contacto = contacto
            registro.telefono = telefono
            registro.accion = accion
            registro.incluir_en_agenda = incluir_en_agenda
            registro.item_id = item_id
            registro.periodo_id = periodo_id
            registro.tipo_id = tipo_id
            registro.subtipo_id = subtipo_id
            registro.save()

            registrar_historial(
                actor=request.user,
                action='Editar actividad AJAX',
                entity=f'Registro:{registro.pk}',
                before=before,
                after=_registro_snapshot(registro),
                period=registro.periodo,
            )
        return JsonResponse({'success': True, 'message': 'La actividad se actualizó correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar la actividad: {str(e)}'}, status=500)
#Funciones de Compromiso

@cargo_required('funcionario', permission='manage_collective_agenda')
def agenda_colectiva(request):
    delegation = active_delegation(request)
    delegation_id = delegation.pk if delegation else None
    if request.method == 'POST' and request.POST.get('action') == 'estado_compromiso':
        if not delegation_id:
            messages.error(request, 'Tu cuenta no tiene una delegación asignada.')
            return redirect('funcionario:agenda_colectiva')
        commitment = get_object_or_404(
            Compromiso.objects.select_related('agenda', 'agenda__periodo').filter(
                agenda__delegacion_id=delegation_id,
                responsable=request.user,
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
        if period_id and period_id.isdecimal():
            return redirect(f"/funcionario/agenda_colectiva/?periodo={int(period_id)}")
        return redirect('funcionario:agenda_colectiva')

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
    if delegation_id and selected_period:
        registros = Registro.objects.filter(
            autor__usuariodelegacion__delegacion_id=delegation_id,
            autor__usuariodelegacion__fecha_fin__isnull=True,
            periodo=selected_period,
            incluir_en_agenda=True,
        ).select_related('autor', 'item').distinct().order_by('-fecha')
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
            agenda__periodo=selected_period,
        ).select_related('agenda', 'agenda__periodo').prefetch_related(
            'responsable', 'evidencias_compromiso',
        )
    return render(request, 'FuncionarioApp/agenda_colectiva.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'periodos': periods,
        'periodo_seleccionado': selected_period,
        'registros': registros,
        'compromisos': commitments,
        'delegation_assigned': bool(delegation_id),
    })


def _compromiso_snapshot(compromiso):
    return {
        'descripcion': compromiso.descripcion,
        'solicitante': compromiso.solicitante,
        'territorio': compromiso.territorio,
        'fecha': compromiso.fecha.isoformat(),
        'observaciones': compromiso.observaciones,
        'tipo_id': compromiso.tipo_id,
        'subtipo_id': compromiso.subtipo_id,
    }


def _compromisos_responsable(request):
    delegation = active_delegation(request)
    if delegation is None:
        return delegation, Compromiso.objects.none()
    return delegation, Compromiso.objects.filter(
        agenda__delegacion=delegation,
        responsable=request.user,
    ).select_related('agenda', 'agenda__periodo').prefetch_related(
        'evidencias_compromiso',
    )


@cargo_required('funcionario', permission='create_employee_commitments')
def nuevo_compromiso(request):
    delegation = active_delegation(request)
    form = FuncionarioCompromisoForm(request.POST or None)
    if request.method == 'POST':
        if delegation is None:
            messages.error(request, 'Asigna una delegación a tu cuenta antes de crear compromisos.')
        elif form.is_valid():
            period = form.cleaned_data['periodo']
            agenda, _ = Agenda.objects.get_or_create(
                delegacion=delegation,
                periodo=period,
            )
            with transaction.atomic():
                commitment = form.save(commit=False)
                commitment.agenda = agenda
                commitment.save()
                commitment.responsable.add(request.user)
                registrar_historial(
                    actor=request.user,
                    action='Crear compromiso como Funcionario',
                    entity=f'Compromiso:{commitment.pk}',
                    after=_compromiso_snapshot(commitment),
                    period=period,
                )
            messages.success(request, 'El compromiso quedó agregado a la agenda.')
            return redirect('funcionario:agenda_colectiva')
        else:
            messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    return render(request, 'FuncionarioApp/compromiso_form.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'compromiso': None,
    })


@cargo_required('funcionario', permission='edit_employee_commitments')
def editar_compromiso(request, compromiso_id):
    delegation, commitments = _compromisos_responsable(request)
    commitment = get_object_or_404(commitments, pk=compromiso_id)
    if commitment.evidencias_compromiso.exists():
        messages.error(request, 'Este compromiso ya tiene evidencias; la edición general está bloqueada.')
        return redirect('funcionario:agenda_colectiva')
    if commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
        messages.error(request, 'Los compromisos de un período cerrado son de solo lectura.')
        return redirect('funcionario:agenda_colectiva')
    form = FuncionarioCompromisoForm(
        request.POST or None,
        instance=commitment,
    )
    if request.method == 'POST' and form.is_valid():
        before = _compromiso_snapshot(commitment)
        with transaction.atomic():
            commitment = form.save(commit=False)
            commitment.save(update_fields=[
                'descripcion', 'solicitante', 'territorio', 'fecha',
                'observaciones', 'tipo', 'subtipo', 'actualizado',
            ])
            registrar_historial(
                actor=request.user,
                action='Modificar compromiso como Funcionario',
                entity=f'Compromiso:{commitment.pk}',
                before=before,
                after=_compromiso_snapshot(commitment),
                period=commitment.agenda.periodo,
            )
        messages.success(request, 'El compromiso se actualizó correctamente.')
        return redirect('funcionario:agenda_colectiva')
    if request.method == 'POST':
        messages.error(request, 'No se pudo guardar. Revisa los campos indicados.')
    return render(request, 'FuncionarioApp/compromiso_form.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'compromiso': commitment,
    })

@cargo_required('funcionario', permission='upload_commitment_evidence')
def cargar_evidencia_compromiso(request, compromiso_id):
    _, commitments = _compromisos_responsable(request)
    commitment = get_object_or_404(commitments, pk=compromiso_id)
    if commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
        messages.error(request, 'Las evidencias de un período cerrado son de solo lectura.')
        return redirect('funcionario:agenda_colectiva')
    form = CompromisoEvidenciaForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            evidence = Evidencia.objects.create(
                archivo=form.cleaned_data['evidencia'],
                compromiso=commitment,
                autor=request.user,
            )
            registrar_historial(
                actor=request.user,
                action='Cargar evidencia de compromiso',
                entity=f'Evidencia:{evidence.pk}',
                after={
                    'codigo': str(evidence.codigo),
                    'compromiso_id': commitment.pk,
                },
                period=commitment.agenda.periodo,
            )
        messages.success(request, 'La evidencia quedó cargada correctamente.')
        return redirect('funcionario:agenda_colectiva')
    if request.method == 'POST':
        messages.error(request, 'No se pudo cargar la evidencia. Revisa el archivo.')
    return render(request, 'FuncionarioApp/evidencia_compromiso_form.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'compromiso': commitment,
    })

#Funciones de Vecinos
def _vecinos_para_usuario(request):
    queryset = Vecino.objects.select_related(
        'delegacion', 'solicitante', 'territorio', 'junta_vecino', 'cargo_jv',
    )
    return filter_by_delegation(
        queryset,
        request,
        delegation_lookup='delegacion_id',
    )

def _delegaciones_para_vecino(request):
    return available_delegations(request.user).filter(
        Q(estado=Delegacion.Estado.ACTIVA)
        | Q(estado__iexact='activo'),
    ).order_by('nombre')

def _vecino_snapshot(vecino):
    return {
        'nombre': vecino.nombre,
        'telefono': vecino.telefono,
        'direccion': vecino.direccion,
        'territorio_id': vecino.territorio_id,
        'delegacion_id': vecino.delegacion_id,
        'solicitante_id': vecino.solicitante_id,
        'junta_vecino_id': vecino.junta_vecino_id,
        'cargo_jv_id': vecino.cargo_jv_id,
        'activo': vecino.activo,
    }

def _vecino_reference_snapshot(record):
    if isinstance(record, Territorio):
        return {
            'nombre': record.nombre,
            'delegacion_id': record.delegacion_id,
        }
    if isinstance(record, JuntaVecino):
        return {
            'nombre': record.nombre,
            'domicilio_legal': record.domicilio_legal,
            'numero_rpj': record.numero_rpj,
            'territorio_id': record.territorio_id,
            'delegacion_id': record.delegacion_id,
        }
    return {
        'nombre': record.nombre,
        'permisos': record.permisos,
        'junta_vecino_id': record.junta_vecino_id,
    }

@cargo_required('funcionario', permission='access_funcionario_vecinos')
def vecinos(request):
    queryset = _vecinos_para_usuario(request)
    search_query = request.GET.get('q', '').strip()
    show_inactive = request.GET.get('inactivos') == '1'
    if not show_inactive:
        queryset = queryset.filter(activo=True)
    if search_query:
        queryset = queryset.filter(
            Q(nombre__icontains=search_query)
            | Q(telefono__icontains=search_query)
            | Q(direccion__icontains=search_query)
            | Q(territorio__nombre__icontains=search_query)
        ).distinct()
    page_obj = Paginator(queryset.order_by('nombre', 'pk'), 20).get_page(
        request.GET.get('page'),
    )
    territorios = (
        _vecinos_para_usuario(request)
        .values_list('territorio__nombre', flat=True)
        .distinct()
        .order_by('territorio')
    )
    return render(request, 'FuncionarioApp/vecinos.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'page_obj': page_obj,
        'search_query': search_query,
        'show_inactive': show_inactive,
        'territorios': territorios,
    })

@cargo_required('funcionario', permission='deactivate_vecinos')
@require_POST
def desactivar_vecino(request, vecino_id):
    vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
    before = _vecino_snapshot(vecino)
    vecino.activo = False
    with transaction.atomic():
        vecino.save(update_fields=['activo', 'actualizado'])
        registrar_historial(
            actor=request.user,
            action='Desactivar vecino',
            entity=f'Vecino:{vecino.pk}',
            before=before,
            after=_vecino_snapshot(vecino),
        )
    messages.success(request, 'Vecino desactivado correctamente.')
    return redirect('funcionario:vecinos')


@cargo_required('funcionario', permission='delete_vecinos')
@require_POST
def eliminar_vecino(request, vecino_id, *, return_url_name='funcionario:vecinos'):
    vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
    before = _vecino_snapshot(vecino)
    entity = f'Vecino:{vecino.pk}'
    try:
        with transaction.atomic():
            vecino.delete()
            registrar_historial(
                actor=request.user,
                action='Eliminar vecino',
                entity=entity,
                before=before,
            )
    except ProtectedError:
        messages.error(request, 'No se puede eliminar el vecino porque tiene registros asociados. Desactívalo en su lugar.')
    else:
        messages.success(request, 'Vecino eliminado correctamente.')
    return redirect(return_url_name)


def _vecino_form(
    request,
    vecino_id=None,
    *,
    return_url_name='funcionario:vecinos',
    sidebar_modules=None,
    sgr_role='Funcionario',
):
    queryset = _vecinos_para_usuario(request)
    vecino = get_object_or_404(queryset, pk=vecino_id) if vecino_id else None
    delegaciones = _delegaciones_para_vecino(request)
    if vecino:
        delegaciones = (
            delegaciones
            | Delegacion.objects.filter(pk=vecino.delegacion_id)
        ).distinct()
        initial = {'delegacion': vecino.delegacion_id}
    else:
        requested_delegation = request.GET.get('delegacion')
        selected_delegation = (
            delegaciones.filter(pk=requested_delegation).first()
            if requested_delegation and requested_delegation.isdecimal()
            else None
        )
        selected_delegation = selected_delegation or active_delegation(request)
        if selected_delegation and not delegaciones.filter(
            pk=selected_delegation.pk,
        ).exists():
            selected_delegation = None
        initial = (
            {'delegacion': selected_delegation.pk}
            if selected_delegation else {}
        )
    form = VecinoForm(
        request.POST or None,
        instance=vecino,
        delegaciones=delegaciones,
        initial=initial,
    )
    if request.method == 'POST' and form.is_valid():
        before = _vecino_snapshot(vecino) if vecino else None
        with transaction.atomic():
            vecino = form.save()
            for related_record in form.created_related_records:
                registrar_historial(
                    actor=request.user,
                    action=f'Crear {related_record._meta.verbose_name}',
                    entity=(
                        f'{related_record.__class__.__name__}:'
                        f'{related_record.pk}'
                    ),
                    after=_vecino_reference_snapshot(related_record),
                )
            registrar_historial(
                actor=request.user,
                action='Editar vecino' if before else 'Crear vecino',
                entity=f'Vecino:{vecino.pk}',
                before=before,
                after=_vecino_snapshot(vecino),
            )
        if _telefono_repetido(vecino):
            messages.warning(request, 'Advertencia: ya existe otro vecino con ese teléfono en la delegación.')
        messages.success(
            request,
            'Vecino actualizado correctamente.' if before else 'Vecino creado correctamente.',
        )
        return redirect(return_url_name)
    territorios = Territorio.objects.filter(
        delegacion__in=delegaciones,
    ).values_list('nombre', flat=True).distinct().order_by('nombre')
    return render(request, 'FuncionarioApp/vecino_form.html', {
        'sgr_role': sgr_role,
        'sidebar_modules': (
            _funcionario_sidebar_modules()
            if sidebar_modules is None else sidebar_modules
        ),
        'return_url_name': return_url_name,
        'form': form,
        'vecino': vecino,
        'territorios': territorios,
    })


@cargo_required('funcionario', permission='manage_vecinos')
def vecino_form(request):
    return _vecino_form(request)

@cargo_required('funcionario', permission='edit_vecinos')
def editar_vecino(request, vecino_id):
    return _vecino_form(request, vecino_id)


@cargo_required('funcionario', permission='view_vecino_detail')
@require_GET
def detalle_vecino_json(request, vecino_id):
    vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
    return JsonResponse({
        'id': vecino.pk,
        'nombre': vecino.nombre,
        'telefono': vecino.telefono or '',
        'direccion': vecino.direccion or '',
        'activo': vecino.activo,
        'cargo_jv_id': vecino.cargo_jv_id,
        'delegacion_id': vecino.delegacion_id,
        'junta_vecino_id': vecino.junta_vecino_id,
        'territorio_id': vecino.territorio_id,
        'estado': vecino.estado,
    })

@cargo_required('funcionario', permission='edit_vecino_ajax')
@require_POST
def editar_vecino_ajax(request, vecino_id):
    vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    telefono = data.get('telefono', '').strip()
    direccion = data.get('direccion', '').strip()
    activo = bool(data.get('activo', True))
    cargo_jv_id = data.get('cargo_jv_id')
    delegacion_id = data.get('delegacion_id')
    junta_vecino_id = data.get('junta_vecino_id')
    territorio_id = data.get('territorio_id')
    estado = data.get('estado', Vecino.Estado.ACTIVADO)

    if not nombre or not delegacion_id or not junta_vecino_id or not territorio_id or not cargo_jv_id:
        return JsonResponse({'success': False, 'message': 'Por favor completa todos los campos obligatorios (*).'}, status=400)

    before = _vecino_snapshot(vecino)
    try:
        with transaction.atomic():
            vecino.nombre = nombre
            vecino.telefono = telefono
            vecino.direccion = direccion
            vecino.activo = activo
            vecino.cargo_jv_id = cargo_jv_id
            vecino.delegacion_id = delegacion_id
            vecino.junta_vecino_id = junta_vecino_id
            vecino.territorio_id = territorio_id
            vecino.estado = estado
            vecino.save()

            registrar_historial(
                actor=request.user,
                action='Editar vecino AJAX',
                entity=f'Vecino:{vecino.pk}',
                before=before,
                after=_vecino_snapshot(vecino),
            )
        return JsonResponse({'success': True, 'message': 'El vecino fue actualizado correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar el vecino: {str(e)}'}, status=500)

#Funciones de Juntas de Vecinos
def _juntas_para_usuario(request):
    queryset = JuntaVecino.objects.select_related('delegacion', 'territorio')
    return filter_by_delegation(
        queryset,
        request,
        delegation_lookup='delegacion_id',
    )


def _delegaciones_para_junta(request):
    return available_delegations(request.user).filter(
        estado=Delegacion.Estado.ACTIVA,
    ).order_by('nombre')

@require_GET
def territorios_por_delegacion(request, delegacion_id):
    territorios = list(
        Territorio.objects.filter(delegacion_id=delegacion_id)
        .order_by('nombre')
        .values('pk', 'nombre')
    )
    return JsonResponse({'territorios': territorios})


def _junta_snapshot(junta):
    return {
        'nombre': junta.nombre,
        'domicilio_legal': junta.domicilio_legal,
        'territorio_id': junta.territorio_id,
        'delegacion_id': junta.delegacion_id,
        'socios_activos': junta.socios_activos,
        'fecha_constitucion': (
            junta.fecha_constitucion.isoformat() if junta.fecha_constitucion else None
        ),
        'numero_rpj': junta.numero_rpj,
        'fecha_ingreso': (
            junta.fecha_ingreso.isoformat() if junta.fecha_ingreso else None
        ),
        'numero_registro': junta.numero_registro,
    }

@cargo_required('funcionario', permission='access_funcionario_juntas')
def juntas(request):
    queryset = _juntas_para_usuario(request)
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(nombre__icontains=search_query)
            | Q(domicilio_legal__icontains=search_query)
            | Q(territorio__nombre__icontains=search_query),
        )
        if search_query.isdecimal():
            queryset = queryset | _juntas_para_usuario(request).filter(
                Q(numero_rpj=int(search_query))
                | Q(numero_registro=int(search_query)),
            )
    page_obj = Paginator(queryset.order_by('nombre', 'pk').distinct(), 20).get_page(
        request.GET.get('page'),
    )
    return render(request, 'FuncionarioApp/juntas.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'page_obj': page_obj,
        'search_query': search_query,
    })


def _junta_form(
    request,
    junta_id=None,
    *,
    return_url_name='funcionario:juntas',
    sidebar_modules=None,
    sgr_role='Funcionario',
):
    queryset = _juntas_para_usuario(request)
    junta = get_object_or_404(queryset, pk=junta_id) if junta_id else None
    delegaciones = _delegaciones_para_junta(request)
    if junta:
        delegaciones = (
            delegaciones
            | Delegacion.objects.filter(pk=junta.delegacion_id)
        ).distinct()
    form = JuntaVecinoForm(
        request.POST or None,
        instance=junta,
        delegaciones=delegaciones,
    )
    if request.method == 'POST' and form.is_valid():
        before = _junta_snapshot(junta) if junta else None
        with transaction.atomic():
            junta = form.save()
            registrar_historial(
                actor=request.user,
                action='Editar junta de vecinos' if before else 'Crear junta de vecinos',
                entity=f'JuntaVecino:{junta.pk}',
                before=before,
                after=_junta_snapshot(junta),
            )
        if JuntaVecino.objects.filter(numero_rpj=junta.numero_rpj).exclude(pk=junta.pk).exists():
            messages.warning(
                request,
                'Advertencia: ya existe otra junta con ese número de personalidad jurídica.',
            )
        messages.success(
            request,
            'Junta actualizada correctamente.' if before else 'Junta creada correctamente.',
        )
        return redirect(return_url_name)
    territorios = Territorio.objects.filter(
        delegacion__in=delegaciones,
    ).values_list('nombre', flat=True).distinct().order_by('nombre')
    return render(request, 'FuncionarioApp/junta_form.html', {
        'sgr_role': sgr_role,
        'sidebar_modules': (
            _funcionario_sidebar_modules()
            if sidebar_modules is None else sidebar_modules
        ),
        'return_url_name': return_url_name,
        'form': form,
        'junta': junta,
        'territorios': territorios,
    })

@cargo_required('admin', 'administrador', permission='create_juntas')
def junta_form(request):
    return _junta_form(request)


@cargo_required('funcionario', permission='edit_juntas')
def editar_junta(request, junta_id):
    return _junta_form(request, junta_id)


@cargo_required('funcionario', permission='view_junta_detail')
@require_GET
def detalle_junta_json(request, junta_id):
    junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
    return JsonResponse({
        'id': junta.pk,
        'nombre': junta.nombre,
        'domicilio_legal': junta.domicilio_legal,
        'socios_activos': junta.socios_activos,
        'fecha_constitucion': junta.fecha_constitucion.strftime('%Y-%m-%dT%H:%M') if junta.fecha_constitucion else '',
        'numero_rpj': junta.numero_rpj,
        'fecha_ingreso': junta.fecha_ingreso.strftime('%Y-%m-%dT%H:%M') if junta.fecha_ingreso else '',
        'numero_registro': junta.numero_registro,
        'delegacion_id': junta.delegacion_id,
        'territorio_id': junta.territorio_id,
    })

@cargo_required('funcionario', permission='edit_junta_ajax')
@require_POST
def editar_junta_ajax(request, junta_id):
    junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    domicilio_legal = data.get('domicilio_legal', '').strip()
    socios_activos = data.get('socios_activos')
    numero_rpj = data.get('numero_rpj')
    numero_registro = data.get('numero_registro') or None
    delegacion_id = data.get('delegacion_id')
    territorio_id = data.get('territorio_id')

    if not nombre or not domicilio_legal or not numero_rpj or not delegacion_id or not territorio_id:
        return JsonResponse({'success': False, 'message': 'Por favor completa los campos obligatorios (*).'}, status=400)

    before = _junta_snapshot(junta)
    try:
        with transaction.atomic():
            junta.nombre = nombre
            junta.domicilio_legal = domicilio_legal
            junta.socios_activos = socios_activos
            junta.numero_rpj = numero_rpj
            junta.numero_registro = numero_registro
            junta.delegacion_id = delegacion_id
            junta.territorio_id = territorio_id
            junta.save()

            registrar_historial(
                actor=request.user,
                action='Editar junta AJAX',
                entity=f'JuntaVecino:{junta.pk}',
                before=before,
                after=_junta_snapshot(junta),
            )
        return JsonResponse({'success': True, 'message': 'La Junta de Vecinos se actualizó correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar la Junta de Vecinos: {str(e)}'}, status=500)

@cargo_required('funcionario', permission='delete_juntas')
@require_POST
def eliminar_junta(
    request,
    junta_id,
    *,
    return_url_name='funcionario:juntas',
):
    junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
    before = _junta_snapshot(junta)
    entity = f'JuntaVecino:{junta.pk}'
    try:
        with transaction.atomic():
            junta.delete()
            registrar_historial(
                actor=request.user,
                action='Eliminar junta de vecinos',
                entity=entity,
                before=before,
            )
    except ProtectedError:
        messages.error(request, 'No se puede eliminar la junta porque tiene vecinos o cargos asociados.')
    else:
        messages.success(request, 'Junta eliminada correctamente.')
    return redirect(return_url_name)

@cargo_required('funcionario', permission='deactivate_juntas')
@require_POST
def junta_desactivar(request, junta_id):
    junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
    before = _junta_snapshot(junta)
    junta.activo = False
    with transaction.atomic():
        junta.save(update_fields=['activo', 'actualizado'])
        registrar_historial(
            actor=request.user,
            action='Desactivar junta de vecinos',
            entity=f'JuntaVecino:{junta.pk}',
            before=before,
            after=_junta_snapshot(junta),
        )
    messages.success(request, 'Junta de vecinos desactivada correctamente.')
    return redirect('funcionario:juntas')

desactivar_junta = junta_desactivar
#Funciones de Atenciones Sociales

@cargo_required('funcionario', permission='manage_social_care')
def atencion_social(request):
    form = AtencionSocialForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            archivo_evidencia = form.cleaned_data.get('evidencia')
            evidencia_obj = None

            # 1. Si se adjuntó archivo, se crea el objeto Evidencia primero
            if archivo_evidencia:
                evidencia_obj = Evidencia.objects.create(
                    archivo=archivo_evidencia
                )

            # 2. Guardar la atención y asignarle la evidencia creada
            gestion, atencion = form.save(autor=request.user)
            if evidencia_obj:
                atencion.evidencia = evidencia_obj
                atencion.save(update_fields=['evidencia'])

            registrar_historial(
                actor=request.user,
                action='Crear atención social',
                entity=f'AtencionSocial:{atencion.pk}',
                after={
                    'beneficiado_id': atencion.beneficiado_id,
                    'tipo_id': atencion.tipo_id,
                    'subtipo_id': atencion.subtipo_id,
                    'gestion_codigo': str(gestion.codigo),
                    'evidencia_codigo': str(evidencia_obj.codigo) if evidencia_obj else None,
                },
            )
        messages.success(request, 'La atención social quedó registrada correctamente.')
        return redirect('funcionario:atencion_social')

    if request.method == 'POST':
        messages.error(request, 'Revisa los datos de la atención indicados en el formulario.')

    # Consulta optimizada con la Foreign Key directa 'evidencia'
    atenciones = AtencionSocial.objects.filter(autor=request.user).select_related(
        'beneficiado', 'tipo', 'subtipo', 'gestion_atencion', 'autor', 'evidencia'
    ).order_by('-fecha')
    
    return render(request, 'FuncionarioApp/atencion_social.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'atenciones': atenciones,
        'atencion_count': atenciones.count(),})

@cargo_required('funcionario', permission='search_social_applicants')
def buscar_solicitantes_vista(request):
    """Vista de plantilla HTML para consultar y listar solicitantes."""
    query = request.GET.get('q', '').strip()
    solicitantes = Beneficiado.objects.none()
    
    if query:
        solicitantes = Beneficiado.objects.annotate(
            telefono_texto=Cast('telefono', output_field=CharField()),
        ).filter(
            Q(nombre__icontains=query)
            | Q(apellido__icontains=query)
            | Q(telefono_texto__icontains=query)
        ).order_by('nombre', 'apellido')

    return render(request, 'FuncionarioApp/buscar_solicitantes.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'solicitantes': solicitantes,
        'query': query,
    })

@cargo_required('funcionario', permission='search_social_applicants')
@require_GET
def buscar_solicitantes(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    results = Beneficiado.objects.annotate(
        telefono_texto=Cast('telefono', output_field=CharField()),
    ).filter(
        Q(nombre__icontains=query)
        | Q(apellido__icontains=query)
        | Q(telefono_texto__icontains=query),
    ).order_by('nombre', 'apellido').values(
        'pk', 'nombre', 'apellido', 'telefono', 'email',
    )[:10]
    return JsonResponse({'results': list(results)})


@cargo_required('funcionario', permission='view_social_subattentions')
@require_GET
def subatenciones_tipo(request, tipo_id):
    subtypes = Subtipo.objects.filter(
        tipo_id=tipo_id,
        estado='ACTIVADO',
    ).order_by('nombre').values('pk', 'nombre')
    return JsonResponse({'results': list(subtypes)})

@cargo_required('funcionario', permission='edit_social_attention_ajax')
@require_POST
def editar_atencion_ajax(request, atencion_id):
    """Procesa la actualización de la atención social desde el modal emergente."""
    atencion = get_object_or_404(AtencionSocial, pk=atencion_id, autor=request.user)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    fecha = data.get('fecha')
    resultado = data.get('resultado', '').strip()
    observaciones = data.get('observaciones', '').strip()
    beneficiado_id = data.get('beneficiado_id')
    tipo_id = data.get('tipo_id')
    subtipo_id = data.get('subtipo_id')
    gestion_atencion_id = data.get('gestion_atencion_id')

    # Validaciones del servidor
    if not fecha or not tipo_id or not subtipo_id or not gestion_atencion_id or not beneficiado_id:
        return JsonResponse({
            'success': False, 
            'message': 'Por favor completa todos los campos obligatorios (*).'
        }, status=400)

    try:
        with transaction.atomic():
            atencion.fecha = fecha
            atencion.resultado = resultado
            atencion.observaciones = observaciones
            atencion.beneficiado_id = beneficiado_id
            atencion.tipo_id = tipo_id
            atencion.subtipo_id = subtipo_id
            atencion.gestion_atencion_id = gestion_atencion_id
            atencion.save()

            registrar_historial(
                actor=request.user,
                action='Editar atención social',
                entity=f'AtencionSocial:{atencion.pk}',
                after={
                    'beneficiado_id': atencion.beneficiado_id,
                    'tipo_id': atencion.tipo_id,
                    'subtipo_id': atencion.subtipo_id,
                    'gestion_id': atencion.gestion_atencion_id,
                },
            )

        return JsonResponse({'success': True, 'message': 'La atención social fue actualizada correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al guardar en el servidor: {str(e)}'}, status=500)

@cargo_required('funcionario', permission='view_social_attention_detail')
@require_GET
def detalle_atencion_json(request, atencion_id):
    """Devuelve los datos reales de la atención social para precargar el modal de edición."""
    atencion = get_object_or_404(AtencionSocial, pk=atencion_id, autor=request.user)
    
    # Formatear la fecha al formato que acepta un <input type="datetime-local"> (YYYY-MM-DDTHH:MM)
    fecha_iso = atencion.fecha.strftime('%Y-%m-%dT%H:%M') if atencion.fecha else ''
    
    subtipos = list(
        Subtipo.objects.filter(tipo_id=atencion.tipo_id, estado='ACTIVADO')
        .order_by('nombre')
        .values('pk', 'nombre')
    )
    
    return JsonResponse({
        'id': atencion.pk,
        'fecha': fecha_iso,
        'resultado': atencion.resultado or '',
        'observaciones': atencion.observaciones or '',
        'beneficiado_id': atencion.beneficiado_id,
        'tipo_id': atencion.tipo_id,
        'subtipo_id': atencion.subtipo_id,
        'gestion_atencion_id': atencion.gestion_atencion_id,
        'subtipos_disponibles': subtipos,
    })


#Funciones de Gestiones Sociales
@cargo_required('funcionario', permission='access_social_cases')
def casos_sociales(request):
    """Vista principal para listar las Gestiones Sociales con conteo de atenciones."""
    gestiones = GestionAtencion.objects.annotate(
        total_atenciones=Count('atencionsocial')
    ).order_by('-fecha', '-id')

    form = GestionAtencionForm()

    return render(request, 'FuncionarioApp/casos_sociales.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'gestiones': gestiones,
        'gestion_count': gestiones.count(),
        'form': form,
    })


@cargo_required('funcionario', permission='create_social_management_ajax')
@require_POST
def crear_gestion_social_ajax(request):
    """Procesa el registro AJAX de una nueva gestión social con código alfanumérico aleatorio."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    fecha = data.get('fecha')
    observaciones = data.get('observaciones', '').strip()

    if not fecha:
        return JsonResponse({'success': False, 'message': 'La fecha es un campo obligatorio.'}, status=400)

    try:
        with transaction.atomic():
            gestion = GestionAtencion.objects.create(
                fecha=fecha,
                observaciones=observaciones
            )
            registrar_historial(
                actor=request.user,
                action='Crear gestión social',
                entity=f'GestionAtencion:{gestion.pk}',
                after={'codigo': str(gestion.codigo), 'fecha': str(gestion.fecha)},
            )

        return JsonResponse({
            'success': True,
            'message': f'Gestión registrada exitosamente con el código: {gestion.codigo}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al registrar la gestión: {str(e)}'}, status=500)


@cargo_required('funcionario', permission='view_social_management_detail')
@require_GET
def detalle_gestion_social_json(request, gestion_id):
    """Obtiene los datos reales de una gestión social para precargar el modal de edición."""
    gestion = get_object_or_404(GestionAtencion, pk=gestion_id)
    return JsonResponse({
        'id': gestion.pk,
        'codigo': gestion.codigo,
        'fecha': gestion.fecha.strftime('%Y-%m-%d') if gestion.fecha else '',
        'observaciones': gestion.observaciones or '',
    })


@cargo_required('funcionario', permission='edit_social_management_ajax')
@require_POST
def editar_gestion_social_ajax(request, gestion_id):
    """Actualiza la fecha y observaciones de una gestión social existente."""
    gestion = get_object_or_404(GestionAtencion, pk=gestion_id)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    fecha = data.get('fecha')
    observaciones = data.get('observaciones', '').strip()

    if not fecha:
        return JsonResponse({'success': False, 'message': 'Por favor ingresa una fecha válida.'}, status=400)

    try:
        with transaction.atomic():
            gestion.fecha = fecha
            gestion.observaciones = observaciones
            gestion.save(update_fields=['fecha', 'observaciones'])

            registrar_historial(
                actor=request.user,
                action='Editar gestión social',
                entity=f'GestionAtencion:{gestion.pk}',
                after={'fecha': str(gestion.fecha), 'observaciones': gestion.observaciones},
            )

        return JsonResponse({'success': True, 'message': 'La gestión social se actualizó correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar: {str(e)}'}, status=500)