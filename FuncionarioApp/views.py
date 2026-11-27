# Importaciones de Django y estándar
from datetime import date
from decimal import Decimal
from datetime import datetime
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
import json

# Importaciones de la aplicación AdminApp
from AdminApp.audit import registrar_historial
from AdminApp.delegation_scope import (available_delegations, filter_by_delegation)
from AdminApp.models import Delegacion
from AdminApp.pagination_utils import paginate_queryset
from AdminApp.views import _admin_dashboard_modules

# Importaciones de la aplicación FuncionarioApp
from FuncionarioApp.models import (Carta,CargoJv,JuntaVecino,Registro,Subtipo,Territorio,Tipo,Vecino,WEEKLY_CLOSURE_MESSAGE,normalizar_telefono,periodo_semanal_abierto,validar_periodo_semanal_abierto)

# Importaciones de la aplicación CoordinadorApp
from CoordinadorApp.models import AtencionSocial, Desempeno, GestionAtencion, Item, Periodo
from CoordinadorApp.services import clasificar_umbral, periodo_vigente, resumen_cumplimiento, umbral_delegacion

# Importaciones de la aplicación DelegadoApp y SupervisorApp
from DelegadoApp.models import Agenda, Compromiso
from DelegadoApp.services import agenda_items, actualizar_compromiso, actualizar_estado_compromiso, detalle_actividades, marcar_compromisos_vencidos
from DelegadoApp.forms import CompromisoEstadoForm
from SupervisorApp.models import Evidencia, ObservacionRegistro
from SupervisorApp.files import validate_evidence_file

# Importaciones de Decoradores y Formularios de FuncionarioApp
from config.decorators import cargo_required
from config.delegations import active_delegation
from FuncionarioApp.forms import (AtencionSocialForm,CartaForm,CompromisoEvidenciaForm,FuncionarioCompromisoForm,GestionAtencionForm,JuntaVecinoForm,RegistroForm,VecinoForm)
from FuncionarioApp.forms import TerritorioForm

from django.utils import timezone

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

    if hasattr(user, 'usuariorol_set'):
        try:
            if user.usuariorol_set.filter(rol__nombre__iregex=r'^encargado (área |area )?social$').exists():
                return True
        except Exception:
            pass

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
        {'label': 'Tubo de Cartas', 'url_name': 'funcionario:tubo_cartas'},
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


def _render_cumplimiento(request):
    assigned_periods = Periodo.objects.all().order_by('-fecha_inicio')
    default_period = periodo_vigente(assigned_periods)
    period_id = request.GET.get('periodo', '').strip()
    selected_period = None

    if period_id and period_id.isdigit():
        selected_period = assigned_periods.filter(pk=int(period_id)).first()

    if selected_period is None:
        selected_period = default_period

    detail_performances = Desempeno.objects.filter(
        usuario=request.user,
        periodo=selected_period,
    ).select_related('item', 'periodo') if selected_period else Desempeno.objects.none()

    sin_informacion = False
    if period_id and period_id.isdigit() and not detail_performances.exists():
        sin_informacion = True

    # El servicio central aplica las mismas reglas de validación, evidencia,
    # tope diario y genera_puntaje que utilizan Delegación y Coordinación.
    summary_detail = resumen_cumplimiento(detail_performances)
    detail_kind = request.GET.get('detalle', '')
    detail_records = detalle_actividades(
        user_ids=[request.user.pk],
        period=selected_period,
    ) if detail_kind else []

    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'periodos': assigned_periods,
        'periodo_seleccionado': selected_period,
        'summary': summary_detail,
        'summary_detail': summary_detail,
        'item_count': len(summary_detail['items']),
        'umbral_delegacion': umbral_delegacion(),
        'clasificacion_umbral': clasificar_umbral(
            summary_detail['avance_real'],
            tiene_items=bool(summary_detail['items']),
        ),
        'sin_informacion': sin_informacion,
        'ultima_actualizacion': timezone.localtime(),
        'detail_kind': detail_kind,
        'detail_records': detail_records,
    })


@cargo_required('funcionario', permission='manage_employee_compliance')
def cumplimiento(request):
    return redirect('funcionario:home')


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
    adding_observation = request.method == 'POST' and request.POST.get('action') == 'agregar_observacion'
    if registration_id:
        registro = get_object_or_404(
            Registro.objects.select_related('periodo'),
            pk=registration_id,
            autor=request.user,
            **({} if adding_observation else {
                'estado': Registro.Estado.PENDIENTE,
                'periodo__estado': Periodo.Estado.ABIERTO,
            }),
        )

    if registro is not None and not adding_observation:
        bloqueo = motivo_bloqueo_registro(registro)
        if bloqueo:
            messages.error(request, bloqueo)
            return redirect('funcionario:gestion_actividades')

    if request.method == 'POST' and request.POST.get('action') == 'agregar_observacion':
        comentario = request.POST.get('comentario', '').strip()
        if not comentario:
            messages.error(request, 'El comentario de la observación es obligatorio.')
        else:
            ObservacionRegistro.objects.create(registro=registro, evidencia=registro.evidencia, autor=request.user, comentario=comentario)
            messages.success(request, 'La observación quedó registrada.')
        return redirect('funcionario:gestion_actividades')

    if request.method == 'POST' and request.POST.get('action') == 'eliminar':
        if registro.evidencia_id:
            messages.error(
                request,
                'No se puede eliminar una actividad que ya tiene evidencia asociada.',
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
            uploaded_file = form.cleaned_data.get('evidencia')
            if uploaded_file:
                evidencia_obj = Evidencia.objects.create(
                    archivo=uploaded_file,
                )
                registro.evidencia = evidencia_obj
            registro.save()

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

    from django.db.models import Case, When, Value, IntegerField
    orden_estado = Case(
        When(estado='validada', then=Value(1)),
        When(estado='anulada', then=Value(2)),
        When(estado='observada', then=Value(3)),
        When(estado='pendiente', then=Value(4)),
        default=Value(5),
        output_field=IntegerField(),
    )

    registros = Registro.objects.filter(autor=request.user).select_related(
        'item', 'periodo', 'tipo', 'subtipo', 'evidencia'
    ).annotate(prioridad_estado=orden_estado).prefetch_related('observaciones_cronologicas__autor')
    filtro_texto = request.GET.get('q', '').strip()
    if filtro_texto:
        registros = registros.filter(Q(descripcion__icontains=filtro_texto) | Q(accion__icontains=filtro_texto) | Q(item__nombre__icontains=filtro_texto))
    if request.GET.get('estado'):
        registros = registros.filter(estado=request.GET['estado'])
    if request.GET.get('desde'):
        registros = registros.filter(fecha__gte=request.GET['desde'])
    if request.GET.get('hasta'):
        registros = registros.filter(fecha__lte=request.GET['hasta'])
    registros, total_registros, pagination_query, sort, direction = paginate_queryset(
        request, registros, default_ordering='fecha',
        allowed_ordering={'fecha': 'fecha', 'creado': 'creado', 'estado': 'estado'},
    )
    # El botón Editar se muestra con las mismas reglas que valida el servidor
    # (período, estado, evidencia y cierre semanal HU-35).
    for reg in registros:
        reg.editable = motivo_bloqueo_registro(reg) is None

    tipos = Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO).order_by('nombre')
    items = Item.objects.filter(estado=Item.Estado.ACTIVO).order_by('nombre')
    periodos = Periodo.objects.all().order_by('-fecha_inicio')

    return render(request, 'FuncionarioApp/index.html', {
        'sgr_role': 'Funcionario',
        'form': form,
        'registros': registros,
        'editing_record': registro,
        'sidebar_modules': _funcionario_sidebar_modules(),
        'registro_count': total_registros,
        'total_encontrados': total_registros,
        'pagination_query': pagination_query,
        'sort': sort,
        'direction': direction,
        'tipos': tipos,
        'items': items,
        'periodos': periodos,
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

    subtipos_qs = Subtipo.objects.filter(tipo_id=registro.tipo_id, estado=Subtipo.Estado.ACTIVADO)
    if registro.subtipo_id:
        subtipos_qs = (subtipos_qs | Subtipo.objects.filter(pk=registro.subtipo_id)).distinct()
    subtipos = list(subtipos_qs.order_by('nombre').values('pk', 'nombre'))

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
        'item_nombre': registro.item.nombre if registro.item else '',
        'periodo_id': registro.periodo_id,
        'periodo_nombre': registro.periodo.nombre if registro.periodo else '',
        'tipo_id': registro.tipo_id,
        'tipo_nombre': registro.tipo.nombre if registro.tipo else '',
        'subtipo_id': registro.subtipo_id,
        'subtipo_nombre': registro.subtipo.nombre if registro.subtipo else '',
        'observaciones': [
            {
                'autor': observation.autor.get_full_name() or observation.autor.email,
                'rol': getattr(getattr(observation.autor, 'cargo', None), 'nombre', '') or 'Usuario',
                'fecha_hora': observation.fecha_hora.isoformat(),
                'comentario': observation.comentario,
            }
            for observation in registro.observaciones_cronologicas.select_related('autor').all()
        ],
        'evidencia_url': registro.evidencia.archivo.url if registro.evidencia and registro.evidencia.archivo else None,
        'subtipos_disponibles': subtipos,
    })


def motivo_bloqueo_registro(registro):
    """Indica por qué una actividad ya no se puede modificar ni eliminar.

    Centraliza las reglas de HU-28 (período cerrado), HU-35 (cierre semanal),
    el flujo de validación (solo pendientes) y el bloqueo por evidencia.
    Retorna ``None`` cuando la actividad es editable.
    """
    if registro.periodo.estado != Periodo.Estado.ABIERTO:
        return 'La actividad pertenece a un período cerrado y no se puede modificar.'
    if registro.estado != Registro.Estado.PENDIENTE:
        return 'Solo se pueden modificar actividades en estado Pendiente.'
    if registro.evidencia_id:
        return 'La actividad ya tiene evidencia asociada; la edición está bloqueada.'
    if not periodo_semanal_abierto(registro.fecha):
        return f'{WEEKLY_CLOSURE_MESSAGE}: la actividad ya no se puede modificar.'
    return None


def _datos_edicion_registro(request):
    """Acepta tanto FormData (lo que envía el modal) como JSON."""
    if request.content_type in ('multipart/form-data', 'application/x-www-form-urlencoded'):
        return request.POST
    return json.loads(request.body or b'{}')


def _texto(data, key):
    return str(data.get(key) or '').strip()


@cargo_required('funcionario', permission='edit_employee_record_ajax')
@require_POST
def editar_registro_ajax(request, registro_id):
    registro = get_object_or_404(
        Registro.objects.select_related('periodo'),
        pk=registro_id,
        autor=request.user,
    )
    bloqueo = motivo_bloqueo_registro(registro)
    if bloqueo:
        return JsonResponse({'success': False, 'message': bloqueo}, status=400)

    try:
        data = _datos_edicion_registro(request)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    fecha = _texto(data, 'fecha')
    descripcion = _texto(data, 'descripcion')
    contacto = _texto(data, 'contacto')
    telefono = _texto(data, 'telefono') or None
    accion = _texto(data, 'accion')
    incluir_en_agenda = _texto(data, 'incluir_en_agenda').casefold() in {'true', '1', 'on', 'si', 'sí'}
    item_id = _texto(data, 'item_id')
    periodo_id = _texto(data, 'periodo_id')
    tipo_id = _texto(data, 'tipo_id')
    subtipo_id = _texto(data, 'subtipo_id')

    if not fecha or not descripcion or not item_id or not periodo_id or not tipo_id or not subtipo_id:
        return JsonResponse({'success': False, 'message': 'Por favor completa todos los campos requeridos (*).'}, status=400)

    try:
        fecha_actividad = date.fromisoformat(fecha)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'La fecha de actividad no es válida.'}, status=400)

    periodo = Periodo.objects.filter(pk=periodo_id, estado=Periodo.Estado.ABIERTO).first() if periodo_id.isdecimal() else None
    if periodo is None:
        return JsonResponse({'success': False, 'message': 'Selecciona un período abierto.'}, status=400)
    if not (tipo_id.isdecimal() and subtipo_id.isdecimal()) or not Subtipo.objects.filter(pk=subtipo_id, tipo_id=tipo_id).exists():
        return JsonResponse({'success': False, 'message': 'El subtipo debe pertenecer al tipo seleccionado.'}, status=400)
    if not item_id.isdecimal() or not Item.objects.filter(pk=item_id).exists():
        return JsonResponse({'success': False, 'message': 'Selecciona un ítem válido.'}, status=400)

    archivo = request.FILES.get('evidencia')
    if archivo:
        try:
            validate_evidence_file(archivo)
        except ValidationError as error:
            return JsonResponse({'success': False, 'message': error.messages[0]}, status=400)

    before = _registro_snapshot(registro)
    registro.fecha = fecha_actividad
    registro.descripcion = descripcion
    registro.contacto = contacto
    registro.telefono = telefono
    registro.accion = accion
    registro.incluir_en_agenda = incluir_en_agenda
    registro.item_id = int(item_id)
    registro.periodo = periodo
    registro.tipo_id = int(tipo_id)
    registro.subtipo_id = int(subtipo_id)
    try:
        # Aplica las reglas del modelo: cierre semanal de la nueva fecha,
        # tope diario de actividades y validación de cada campo.
        registro.full_clean()
    except ValidationError as error:
        return JsonResponse({'success': False, 'message': ' '.join(error.messages)}, status=400)

    try:
        with transaction.atomic():
            if archivo:
                registro.evidencia = Evidencia.objects.create(archivo=archivo)
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


@cargo_required('funcionario', permission='manage_collective_agenda')
def agenda_colectiva(request):
    """Vista unificada de Agenda Colectiva: creación de compromisos, listado con búsqueda AJAX y edición en modal."""
    delegation = active_delegation(request)
    delegation_id = delegation.pk if delegation else None

    periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO).order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    selected_period = (periods.filter(pk=int(period_id)).first()
        if period_id.isdecimal()
        else periodo_vigente(periods)
    )

    initial_data = {}
    if selected_period:
        initial_data['periodo'] = selected_period.pk
    now_local = timezone.localtime()
    initial_data['fecha_solicitud'] = now_local.strftime('%Y-%m-%dT%H:%M')
    initial_data['fecha_compromiso'] = now_local.strftime('%Y-%m-%dT%H:%M')
    initial_data['mes'] = now_local.month

    form = FuncionarioCompromisoForm(request.POST or None,delegation=delegation,initial=initial_data)

    # Creación directa desde el formulario superior
    if request.method == 'POST' and request.POST.get('action', 'crear_compromiso') == 'crear_compromiso':
        if not delegation:
            messages.error(request, 'Tu cuenta no tiene una delegación activa asignada.')
            return redirect('funcionario:agenda_colectiva')

        if form.is_valid():
            period = form.cleaned_data['periodo']
            with transaction.atomic():
                agenda, _ = Agenda.objects.get_or_create(
                    delegacion=delegation,
                    periodo=period,
                )
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
            messages.success(request, f'Compromiso {commitment.codigo_publico} registrado en la agenda colectiva.')
            return redirect(f"/funcionario/agenda_colectiva/?periodo={period.pk}")
        else:
            errores = '; '.join(
                f"{campo}: {', '.join(msgs)}" for campo, msgs in form.errors.items()
            )
            messages.error(request, f'No se pudo guardar el compromiso: {errores}')

    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado_filtro', '').strip()
    commitments = Compromiso.objects.none()

    if delegation_id and selected_period:
        commitments_scope = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
            agenda__periodo=selected_period,
        )
        marcar_compromisos_vencidos(commitments_scope, request.user)

        commitments = commitments_scope.select_related('agenda', 'agenda__periodo', 'solicitante', 'territorio', 'tipo', 'subtipo', 'evidencia'
        ).prefetch_related('responsable').order_by('-fecha_compromiso', '-pk')

        if query:
            commitments = commitments.filter(
                Q(descripcion__icontains=query)
                | Q(solicitante__nombre__icontains=query)
                | Q(solicitante__apellido__icontains=query)
                | Q(territorio__nombre__icontains=query)
                | Q(area_apoyo__icontains=query)
            )
        if estado_filtro:
            commitments = commitments.filter(estado=estado_filtro)

    page_obj = Paginator(commitments, 15).get_page(request.GET.get('page'))

    # Marcar qué compromisos puede editar el usuario actual
    for item in page_obj:
        es_responsable = any(u.pk == request.user.pk for u in item.responsable.all())
        periodo_abierto = item.agenda.periodo.estado == Periodo.Estado.ABIERTO
        item.puede_editar = es_responsable and periodo_abierto and not bool(item.evidencia_id)

    tipos = Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO).order_by('nombre')
    vecinos = Vecino.objects.filter(activo=True).order_by('nombre', 'apellido')
    territorios = Territorio.objects.filter(delegacion=delegation).order_by('nombre') if delegation else Territorio.objects.none()
    registros = Registro.objects.none()
    agenda_results = []
    if delegation_id and selected_period:
        registros = Registro.objects.filter(autor__usuariodelegacion__delegacion_id=delegation_id,autor__usuariodelegacion__fecha_fin__isnull=True,periodo=selected_period,incluir_en_agenda=True,).select_related('autor', 'item').distinct().order_by('-fecha')
        agenda_results = agenda_items(
            delegation_id=delegation_id,
            period=selected_period,
            query=query,
            actor=request.user,
        )
    return render(request, 'FuncionarioApp/agenda_colectiva.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'periodos': periods,
        'periodo_seleccionado': selected_period,
        'page_obj': page_obj,
        'delegation_assigned': bool(delegation_id),
        'query': query,
        'estado_filtro': estado_filtro,
        'estados_choices': Compromiso.Estado.choices,
        'ambitos_choices': Compromiso.Ambito.choices,
        'tipos': tipos,
        'vecinos': vecinos,
        'territorios': territorios,
        'registros' : registros,
        'agenda_results' : agenda_results,
    })


@cargo_required('funcionario', permission='search_collective_commitments_ajax')
@require_GET
def buscar_compromisos_ajax(request):
    """Buscador AJAX en vivo (keyup) para filtrar compromisos de la agenda colectiva."""
    delegation = active_delegation(request)
    periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO).order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    selected_period = periods.filter(pk=int(period_id)).first() if period_id.isdecimal() else periodo_vigente(periods)

    if not delegation or not selected_period:
        return JsonResponse({'success': True, 'compromisos': []})

    query = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()

    commitments_scope = Compromiso.objects.filter(agenda__delegacion=delegation,agenda__periodo=selected_period,)
    marcar_compromisos_vencidos(commitments_scope, request.user)

    qs = commitments_scope.select_related('agenda__periodo', 'solicitante', 'territorio', 'tipo', 'subtipo', 'evidencia'
    ).prefetch_related('responsable').order_by('-fecha_compromiso', '-pk')

    if query:
        qs = qs.filter(
            Q(descripcion__icontains=query)
            | Q(solicitante__nombre__icontains=query)
            | Q(solicitante__apellido__icontains=query)
            | Q(territorio__nombre__icontains=query)
            | Q(area_apoyo__icontains=query)
        )
    if estado_filtro:
        qs = qs.filter(estado=estado_filtro)

    resultados = []
    for c in qs[:50]:
        es_responsable = any(u.pk == request.user.pk for u in c.responsable.all())
        puede_editar = es_responsable and (c.agenda.periodo.estado == Periodo.Estado.ABIERTO) and not bool(c.evidencia_id)
        responsables_str = ', '.join(
            (u.get_full_name() or u.email) for u in c.responsable.all()
        ) or 'Sin asignar'
        solicitante_str = f"{c.solicitante.nombre} {c.solicitante.apellido or ''}".strip() if c.solicitante else '—'

        resultados.append({
            'id': c.pk,
            'codigo': c.codigo_publico,
            'descripcion': c.descripcion,
            'solicitante': solicitante_str,
            'territorio': c.territorio.nombre if c.territorio else '—',
            'observaciones': c.observaciones or '—',
            'genera_puntaje': 'Sí' if (c.genera_puntaje and c.genera_puntaje > 0) else 'No',
            'tipo': c.tipo.nombre if c.tipo else '—',
            'subtipo': c.subtipo.nombre if c.subtipo else '—',
            'ambito': c.get_ambito_display(),
            'area_apoyo': c.area_apoyo or '—',
            'fecha_compromiso': timezone.localtime(c.fecha_compromiso).strftime('%d/%m/%Y %H:%M') if c.fecha_compromiso else '—',
            'fecha_solicitud': timezone.localtime(c.fecha_solicitud).strftime('%d/%m/%Y %H:%M') if c.fecha_solicitud else '—',
            'evidencia_id': c.evidencia.pk if c.evidencia_id else None,
            'evidencia_codigo': str(c.evidencia.codigo) if (c.evidencia_id and getattr(c.evidencia, 'codigo', None)) else (f"EV-{c.evidencia.pk}" if c.evidencia_id else None),
            'evidencia_url': c.evidencia.archivo.url if (c.evidencia_id and c.evidencia.archivo) else None,
            'estado': c.estado,
            'estado_display': c.get_estado_display(),
            'puede_editar': puede_editar,
        })
    return JsonResponse({'success': True, 'compromisos': resultados})


def _compromiso_snapshot(compromiso):
    return {
        'periodo_id': compromiso.agenda.periodo_id if compromiso.agenda_id else None,
        'descripcion': compromiso.descripcion,
        'fecha_solicitud': compromiso.fecha_solicitud.isoformat() if compromiso.fecha_solicitud else None,
        'fecha_compromiso': compromiso.fecha_compromiso.isoformat() if compromiso.fecha_compromiso else None,
        'mes': compromiso.mes,
        'ambito': compromiso.ambito,
        'solicitante_id': compromiso.solicitante_id,
        'territorio_id': compromiso.territorio_id,
        'area_apoyo': compromiso.area_apoyo,
        'observaciones': compromiso.observaciones,
        'estado': compromiso.estado,
        'tipo_id': compromiso.tipo_id,
        'subtipo_id': compromiso.subtipo_id,
        'responsable_ids': sorted(compromiso.responsable.values_list('pk', flat=True)),
    }

@cargo_required('funcionario', permission='view_collective_commitment_detail')
@require_GET
def detalle_compromiso_json(request, compromiso_id):
    """Retorna los datos del compromiso en JSON para precargar el modal de edición."""
    delegation = active_delegation(request)
    commitment = get_object_or_404(Compromiso.objects.select_related('agenda', 'agenda__periodo'),pk=compromiso_id,agenda__delegacion=delegation)

    subtipos_qs = Subtipo.objects.filter(tipo_id=commitment.tipo_id, estado=Subtipo.Estado.ACTIVADO)
    if commitment.subtipo_id:
        subtipos_qs = (subtipos_qs | Subtipo.objects.filter(pk=commitment.subtipo_id)).distinct()
    subtipos = list(subtipos_qs.order_by('nombre').values('pk', 'nombre'))

    return JsonResponse({
        'id': commitment.pk,
        'codigo': commitment.codigo_publico,
        'periodo_id': commitment.agenda.periodo_id,
        'descripcion': commitment.descripcion,
        'fecha_solicitud': timezone.localtime(commitment.fecha_solicitud).strftime('%Y-%m-%dT%H:%M') if commitment.fecha_solicitud else '',
        'fecha_compromiso': timezone.localtime(commitment.fecha_compromiso).strftime('%Y-%m-%dT%H:%M') if commitment.fecha_compromiso else '',
        'ambito': commitment.ambito,
        'solicitante_id': commitment.solicitante_id or '',
        'territorio_id': commitment.territorio_id or '',
        'area_apoyo': commitment.area_apoyo or '',
        'mes': commitment.mes,
        'tipo_id': commitment.tipo_id or '',
        'subtipo_id': commitment.subtipo_id or '',
        'estado': commitment.estado,
        'observaciones': commitment.observaciones or '',
        'subtipos_disponibles': subtipos,
    })

@cargo_required('funcionario', permission='search_collective_agenda')
@require_GET
def agenda_busqueda_json(request):
    delegation = active_delegation(request)
    periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO).order_by('-fecha_inicio')
    period_id = request.GET.get('periodo', '')
    period = periods.filter(pk=int(period_id)).first() if period_id.isdecimal() else periodo_vigente(periods)
    if not delegation or not period:
        return JsonResponse({'results': []})
    marcar_compromisos_vencidos(
        Compromiso.objects.filter(agenda__delegacion_id=delegation.pk, agenda__periodo=period),
        request.user,
    )
    return JsonResponse({'results': agenda_items(
        delegation_id=delegation.pk,
        period=period,
        query=request.GET.get('q', '').strip(),
        actor=request.user,
    )})


@cargo_required('funcionario', permission='edit_collective_commitment_ajax')
@require_POST
def editar_compromiso_ajax(request, compromiso_id):
    """Actualiza el compromiso vía AJAX desde el modal, validando reglas de negocio y auditando."""
    delegation, commitments = _compromisos_responsable(request)
    commitment = get_object_or_404(commitments, pk=compromiso_id)

    if bool(commitment.evidencia_id):
        return JsonResponse({'success': False, 'message': 'Este compromiso ya tiene evidencia asociada; la edición está bloqueada.'}, status=400)

    if commitment.agenda.periodo.estado != Periodo.Estado.ABIERTO:
        return JsonResponse({'success': False, 'message': 'Los compromisos de un período cerrado son de solo lectura.'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    descripcion = data.get('descripcion', '').strip()
    fecha_solicitud_raw = data.get('fecha_solicitud')
    fecha_compromiso_raw = data.get('fecha_compromiso')
    ambito = data.get('ambito', Compromiso.Ambito.EXTERNO)
    solicitante_id = data.get('solicitante_id') or None
    territorio_id = data.get('territorio_id') or None
    area_apoyo = data.get('area_apoyo', '').strip()
    mes_raw = data.get('mes')
    tipo_id = data.get('tipo_id') or None
    subtipo_id = data.get('subtipo_id') or None
    estado = data.get('estado', commitment.estado)
    observaciones = data.get('observaciones', '').strip()
    periodo_id = data.get('periodo_id') or commitment.agenda.periodo_id

    if not descripcion or not fecha_solicitud_raw or not fecha_compromiso_raw:
        return JsonResponse({'success': False, 'message': 'La descripción, fecha de solicitud y fecha de compromiso son obligatorias.'}, status=400)

    
    try:
        fecha_sol = timezone.make_aware(datetime.fromisoformat(fecha_solicitud_raw))
        fecha_comp = timezone.make_aware(datetime.fromisoformat(fecha_compromiso_raw))
    except ValueError:
        return JsonResponse({'success': False, 'message': 'El formato de fecha y hora ingresado no es válido.'}, status=400)

    if fecha_comp < fecha_sol:
        return JsonResponse({'success': False, 'message': 'La fecha de compromiso no puede ser anterior a la fecha de solicitud.'}, status=400)

    # Validar mes entre 1 y 12 (si viene vacío, hereda el mes de fecha_compromiso)
    if mes_raw not in (None, ''):
        try:
            mes = int(mes_raw)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'El mes debe ser un número entero entre 1 y 12.'}, status=400)
        if not (1 <= mes <= 12):
            return JsonResponse({'success': False, 'message': 'El mes debe estar entre 1 y 12.'}, status=400)
    else:
        mes = fecha_comp.month

    # Validar coherencia entre tipo y subtipo
    if tipo_id and subtipo_id:
        if not Subtipo.objects.filter(pk=subtipo_id, tipo_id=tipo_id).exists():
            return JsonResponse({'success': False, 'message': 'El subtipo seleccionado no pertenece al tipo elegido.'}, status=400)
    elif tipo_id or subtipo_id:
        return JsonResponse({'success': False, 'message': 'Debes seleccionar tanto el tipo como el subtipo.'}, status=400)

    valid_estados = {choice[0] for choice in Compromiso.Estado.choices}
    if estado not in valid_estados:
        return JsonResponse({'success': False, 'message': 'El estado seleccionado no es válido.'}, status=400)

    valid_ambitos = {choice[0] for choice in Compromiso.Ambito.choices}
    if ambito not in valid_ambitos:
        return JsonResponse({'success': False, 'message': 'El ámbito seleccionado no es válido.'}, status=400)

    period = get_object_or_404(Periodo, pk=periodo_id, estado=Periodo.Estado.ABIERTO)
    before = _compromiso_snapshot(commitment)
    estado_anterior = commitment.estado
    try:
        with transaction.atomic():
            agenda, _ = Agenda.objects.get_or_create(delegacion=delegation, periodo=period)
            commitment.agenda = agenda
            commitment.descripcion = descripcion
            commitment.fecha_solicitud = fecha_sol
            commitment.fecha_compromiso = fecha_comp
            commitment.mes = mes
            commitment.ambito = ambito
            commitment.solicitante_id = solicitante_id
            commitment.territorio_id = territorio_id
            commitment.area_apoyo = area_apoyo
            commitment.observaciones = observaciones
            commitment.estado = estado

            if tipo_id and subtipo_id:
                commitment.tipo_id = tipo_id
                commitment.subtipo_id = subtipo_id

            commitment.save()

            if estado_anterior != estado:
                from DelegadoApp.models import HistorialEstadoCompromiso
                HistorialEstadoCompromiso.objects.create(
                    compromiso=commitment,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado,
                    autor=request.user,
                )

            registrar_historial(
                actor=request.user,
                action='Modificar compromiso como Funcionario (AJAX)',
                entity=f'Compromiso:{commitment.pk}',
                before=before,
                after=_compromiso_snapshot(commitment),
                period=period,
            )
        return JsonResponse({
            'success': True,
            'message': f'El compromiso {commitment.codigo_publico} se actualizó correctamente.',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar el compromiso: {str(e)}'}, status=500)


def _compromisos_responsable(request):
    delegation = active_delegation(request)
    if delegation is None:
        return delegation, Compromiso.objects.none()
    return delegation, Compromiso.objects.filter(
        agenda__delegacion=delegation,
        responsable=request.user,
    ).select_related('agenda', 'agenda__periodo')





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
            )
            commitment.evidencia = evidence
            commitment.save(update_fields=['evidencia']
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


def _vecinos_para_usuario(request):
    queryset = Vecino.objects.select_related(
        'delegacion', 'territorio', 'junta_vecino',
    ).prefetch_related('cargos_ejercidos')
    return filter_by_delegation(
        queryset,
        request,
        delegation_lookup='delegacion_id',
    )


def _delegaciones_para_vecino(request):
    """Permite seleccionar cualquier delegación activa existente en el sistema."""
    return Delegacion.objects.filter(
        Q(estado=Delegacion.Estado.ACTIVADO)
        | Q(estado__iexact='activo')
    ).order_by('nombre')


def _vecino_snapshot(vecino):
    return {
        'rut': vecino.rut,
        'nombre': vecino.nombre,
        'telefono': vecino.telefono,
        'direccion': vecino.direccion,
        'territorio_id': vecino.territorio_id,
        'delegacion_id': vecino.delegacion_id,
        'junta_vecino_id': vecino.junta_vecino_id,
        'estado': vecino.estado,
        'activo': vecino.activo,
    }


@cargo_required('funcionario', permission='access_funcionario_vecinos')
def vecinos(request):
    queryset = Vecino.objects.select_related(
        'delegacion', 'territorio', 'junta_vecino',
    ).prefetch_related('cargos_ejercidos')

    delegaciones = _delegaciones_para_vecino(request)
    selected_delegation = active_delegation(request)
    initial = (
        {'delegacion': selected_delegation.pk}
        if selected_delegation and delegaciones.filter(pk=selected_delegation.pk).exists()
        else {}
    )

    form = VecinoForm(request.POST or None, delegaciones=delegaciones, initial=initial)

    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                vecino = form.save()
                cargo_obj = form.cleaned_data.get('cargo_jv') if form.cleaned_data.get('es_dirigente') else None
                if cargo_obj:
                    CargoJv.objects.filter(pk=cargo_obj.pk).update(vecino=vecino)

                registrar_historial(
                    actor=request.user,
                    action='Crear vecino',
                    entity=f'Vecino:{vecino.pk}',
                    after=_vecino_snapshot(vecino),
                )
            if _telefono_repetido(vecino):
                messages.warning(request, 'Advertencia: ya existe otro vecino con ese teléfono en la delegación.')
            messages.success(request, 'Vecino creado correctamente.')
            return redirect('funcionario:vecinos')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error en {field}: {error}")

    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(rut__icontains=search_query)
            | Q(nombre__icontains=search_query)
            | Q(telefono__icontains=search_query)
            | Q(direccion__icontains=search_query)
            | Q(territorio__nombre__icontains=search_query)
            | Q(junta_vecino__nombre__icontains=search_query)
        ).distinct()
    if request.GET.get('territorio'):
        queryset = queryset.filter(territorio_id=request.GET['territorio'])
    if request.GET.get('delegacion'):
        queryset = queryset.filter(delegacion_id=request.GET['delegacion'])
    if request.GET.get('estado'):
        queryset = queryset.filter(estado=request.GET['estado'])
    if request.GET.get('desde'):
        queryset = queryset.filter(creado__date__gte=request.GET['desde'])
    if request.GET.get('hasta'):
        queryset = queryset.filter(creado__date__lte=request.GET['hasta'])

    page_obj, total_encontrados, pagination_query, sort, direction = paginate_queryset(
        request, queryset, default_ordering='nombre',
        allowed_ordering={'nombre': 'nombre', 'territorio': 'territorio__nombre', 'estado': 'estado'},
    )
    territorios = (
        Territorio.objects.filter(delegacion__in=delegaciones)
        .values_list('nombre', flat=True)
        .distinct()
        .order_by('nombre')
    )

    return render(request, 'FuncionarioApp/vecinos.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'vecinos': page_obj,
        'page_obj': page_obj,
        'delegaciones': delegaciones,
        'search_query': search_query,
        'territorios': territorios,
        'total_encontrados': total_encontrados,
        'pagination_query': pagination_query,
        'sort': sort,
        'direction': direction,
    })


@cargo_required('funcionario', permission='deactivate_vecinos')
@require_POST
def desactivar_vecino(request, vecino_id):
    vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
    before = _vecino_snapshot(vecino)
    vecino.activo = False
    vecino.estado = Vecino.Estado.DESACTIVADO
    with transaction.atomic():
        vecino.save(update_fields=['activo', 'estado', 'actualizado'])
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


def _vecino_form(request, vecino_id=None, *, return_url_name='funcionario:vecinos', sidebar_modules=None, sgr_role='Funcionario'):
    queryset = Vecino.objects.select_related('delegacion', 'territorio', 'junta_vecino').prefetch_related('cargos_ejercidos')
    vecino = get_object_or_404(queryset, pk=vecino_id) if vecino_id else None

    delegaciones = _delegaciones_para_vecino(request)
    if vecino:
        delegaciones = (delegaciones | Delegacion.objects.filter(pk=vecino.delegacion_id)).distinct()
        cargo_actual = vecino.cargos_ejercidos.first()
        initial = {
            'delegacion': vecino.delegacion_id,
            'es_dirigente': bool(cargo_actual),
            'cargo_jv': cargo_actual.pk if cargo_actual else None,
        }
    else:
        selected_delegation = active_delegation(request)
        initial = {'delegacion': selected_delegation.pk} if selected_delegation else {}

    form = VecinoForm(request.POST or None, instance=vecino, delegaciones=delegaciones, initial=initial)

    if request.method == 'POST' and form.is_valid():
        before = _vecino_snapshot(vecino) if vecino else None
        with transaction.atomic():
            vecino = form.save()
            CargoJv.objects.filter(vecino=vecino).update(vecino=None)
            cargo_obj = form.cleaned_data.get('cargo_jv') if form.cleaned_data.get('es_dirigente') else None
            if cargo_obj:
                CargoJv.objects.filter(pk=cargo_obj.pk).update(vecino=vecino)

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

    territorios = (
        Territorio.objects.filter(delegacion__in=delegaciones)
        .values_list('nombre', flat=True)
        .distinct()
        .order_by('nombre')
    )

    return render(request, 'FuncionarioApp/vecino_form.html', {
        'sgr_role': sgr_role,
        'sidebar_modules': sidebar_modules or _funcionario_sidebar_modules(),
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
    vecino = get_object_or_404(Vecino.objects.prefetch_related('cargos_ejercidos'),pk=vecino_id,)
    
    nombre_completo = f"{vecino.nombre} {vecino.apellido or ''}".strip()
    cargo_actual = vecino.cargos_ejercidos.first()
    return JsonResponse({
        'id': vecino.pk,
        'rut': vecino.rut or '',
        'nombre': vecino.nombre,
        'apellido' : vecino.apellido,
        'nombre_completo' : nombre_completo,
        'telefono': vecino.telefono or '',
        'direccion': vecino.direccion or '',
        'activo': vecino.activo,
        'es_dirigente': bool(cargo_actual),
        'cargo_jv_id': cargo_actual.pk if cargo_actual else '',
        'delegacion_id': vecino.delegacion_id,
        'junta_vecino_id': vecino.junta_vecino_id,
        'territorio_id': vecino.territorio_id,
        'estado': vecino.estado,
    })


@cargo_required('funcionario', permission='edit_vecino_ajax')
@require_POST
def editar_vecino_ajax(request, vecino_id):
    vecino = get_object_or_404(Vecino, pk=vecino_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    rut = data.get('rut', '').strip().replace('.', '').upper()
    nombre = data.get('nombre', '').strip()
    telefono = data.get('telefono', '').strip()
    direccion = data.get('direccion', '').strip()
    es_dirigente = bool(data.get('es_dirigente', False))
    cargo_jv_id = data.get('cargo_jv_id') if es_dirigente else None
    delegacion_id = data.get('delegacion_id')
    junta_vecino_id = data.get('junta_vecino_id')
    territorio_id = data.get('territorio_id')
    estado = data.get('estado', Vecino.Estado.ACTIVADO)

    if not rut or not nombre or not delegacion_id or not junta_vecino_id or not territorio_id:
        return JsonResponse({'success': False, 'message': 'Por favor completa todos los campos obligatorios (*).'}, status=400)

    if es_dirigente and not cargo_jv_id:
        return JsonResponse({'success': False, 'message': 'Debes seleccionar un cargo si el vecino es dirigente.'}, status=400)

    before = _vecino_snapshot(vecino)
    try:
        with transaction.atomic():
            vecino.rut = rut
            vecino.nombre = nombre
            vecino.telefono = telefono
            vecino.direccion = direccion
            vecino.delegacion_id = delegacion_id
            vecino.junta_vecino_id = junta_vecino_id
            vecino.territorio_id = territorio_id
            vecino.estado = estado
            vecino.activo = (estado == Vecino.Estado.ACTIVADO)
            vecino.save()

            CargoJv.objects.filter(vecino=vecino).update(vecino=None)
            if cargo_jv_id:
                CargoJv.objects.filter(pk=cargo_jv_id).update(vecino=vecino)

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


def _juntas_para_usuario(request):
    queryset = JuntaVecino.objects.select_related('delegacion', 'territorio')
    return filter_by_delegation(
        queryset,
        request,
        delegation_lookup='delegacion_id',
    )


def _delegaciones_para_junta(request):
    return available_delegations(request.user).filter(
        estado=Delegacion.Estado.ACTIVADO,
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
    delegaciones = _delegaciones_para_junta(request)

    form = JuntaVecinoForm(
        request.POST or None,
        delegaciones=delegaciones,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            junta = form.save()
            registrar_historial(
                actor=request.user,
                action='Crear junta de vecinos',
                entity=f'JuntaVecino:{junta.pk}',
                after=_junta_snapshot(junta),
            )
        if JuntaVecino.objects.filter(numero_rpj=junta.numero_rpj).exclude(pk=junta.pk).exists():
            messages.warning(
                request,
                'Advertencia: ya existe otra junta con ese número de personalidad jurídica.',
            )
        messages.success(request, 'Junta creada correctamente.')
        return redirect('funcionario:juntas')

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
        'form': form,
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


@cargo_required('funcionario', permission='manage_social_care')
def atencion_social(request):
    form = AtencionSocialForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            archivo_evidencia = form.cleaned_data.get('evidencia')
            evidencia_obj = None

            if archivo_evidencia:
                evidencia_obj = Evidencia.objects.create(
                    archivo=archivo_evidencia
                )

            gestion, atencion = form.save(autor=request.user)
            if evidencia_obj:
                atencion.evidencia = evidencia_obj
                atencion.save(update_fields=['evidencia'])

            registrar_historial(
                actor=request.user,
                action='Crear atención social',
                entity=f'AtencionSocial:{atencion.pk}',
                after={
                    'vecino_id': atencion.vecino_id,
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

    atenciones = AtencionSocial.objects.filter(autor=request.user).select_related(
        'vecino', 'tipo', 'subtipo', 'gestion_atencion', 'autor', 'evidencia'
    ).order_by('-fecha')

    return render(request, 'FuncionarioApp/atencion_social.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'form': form,
        'atenciones': atenciones,
        'atencion_count': atenciones.count(),
    })


@cargo_required('funcionario', permission='search_social_applicants')
def buscar_solicitantes_vista(request):
    """Vista de plantilla HTML para consultar y listar solicitantes."""
    query = request.GET.get('q', '').strip()
    solicitantes = Vecino.objects.none()

    if query:
        solicitantes = Vecino.objects.filter(
            Q(nombre__icontains=query)
            | Q(telefono__icontains=query)
            | Q(rut__icontains=query)
        ).order_by('nombre')

    return render(request, 'FuncionarioApp/buscar_solicitantes.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'solicitantes': solicitantes,
        'query': query,
    })


@cargo_required('funcionario', permission='autocomplete_social_applicants')
@require_GET
def buscar_solicitantes(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    results = Vecino.objects.filter(
        Q(nombre__icontains=query)
        | Q(telefono__icontains=query)
        | Q(rut__icontains=query)
    ).order_by('nombre').values('pk', 'nombre', 'telefono', 'email', 'rut')[:10]
    formatted_results = []
    for r in results:
        formatted_results.append({
            'pk': r['pk'],
            'nombre': r['nombre'],
            'apellido': '',
            'telefono': r['telefono'] or '',
            'email': r['email'] or '',
        })
    return JsonResponse({'results': formatted_results})


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
    vecino_id = data.get('vecino_id') or data.get('beneficiado_id')
    tipo_id = data.get('tipo_id')
    subtipo_id = data.get('subtipo_id')
    gestion_atencion_id = data.get('gestion_atencion_id')
    etapa = data.get('etapa')

    if not fecha or not tipo_id or not subtipo_id or not gestion_atencion_id or not vecino_id or not etapa:
        return JsonResponse({
            'success': False,
            'message': 'Por favor completa todos los campos obligatorios (*).'
        }, status=400)

    try:
        etapa = int(etapa)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Etapa inválida.'}, status=400)

    if AtencionSocial.objects.filter(gestion_atencion_id=gestion_atencion_id, etapa=etapa).exclude(pk=atencion.pk).exists():
        return JsonResponse({
            'success': False,
            'message': f'La etapa {etapa} ya se encuentra registrada en esta gestión social.'
        }, status=400)

    try:
        with transaction.atomic():
            atencion.fecha = fecha
            atencion.resultado = resultado
            atencion.observaciones = observaciones
            atencion.vecino_id = vecino_id
            atencion.tipo_id = tipo_id
            atencion.subtipo_id = subtipo_id
            atencion.gestion_atencion_id = gestion_atencion_id
            atencion.etapa = etapa
            atencion.save()

            registrar_historial(
                actor=request.user,
                action='Editar atención social',
                entity=f'AtencionSocial:{atencion.pk}',
                after={
                    'vecino_id': atencion.vecino_id,
                    'tipo_id': atencion.tipo_id,
                    'subtipo_id': atencion.subtipo_id,
                    'gestion_id': atencion.gestion_atencion_id,
                    'etapa': atencion.etapa,
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

    fecha_iso = atencion.fecha.strftime('%Y-%m-%dT%H:%M') if atencion.fecha else ''

    subtipos_qs = Subtipo.objects.filter(tipo_id=atencion.tipo_id, estado='ACTIVADO')
    if atencion.subtipo_id:
        subtipos_qs = (subtipos_qs | Subtipo.objects.filter(pk=atencion.subtipo_id)).distinct()
    subtipos = list(subtipos_qs.order_by('nombre').values('pk', 'nombre'))

    return JsonResponse({
        'id': atencion.pk,
        'etapa': atencion.etapa,
        'fecha': fecha_iso,
        'resultado': atencion.resultado or '',
        'observaciones': atencion.observaciones or '',
        'vecino_id': atencion.vecino_id,
        'beneficiado_id': atencion.vecino_id,
        'tipo_id': atencion.tipo_id,
        'subtipo_id': atencion.subtipo_id,
        'gestion_atencion_id': atencion.gestion_atencion_id,
        'subtipos_disponibles': subtipos,
    })


@cargo_required('funcionario', permission='access_social_cases')
def casos_sociales(request):
    """Vista principal para listar las Gestiones Sociales con conteo de atenciones."""
    gestiones = GestionAtencion.objects.annotate(total_atenciones=Count('atencionsocial'))
    if request.GET.get('q'):
        gestiones = gestiones.filter(Q(nombre__icontains=request.GET['q']) | Q(codigo__icontains=request.GET['q']))
    if request.GET.get('desde'):
        gestiones = gestiones.filter(fecha__gte=request.GET['desde'])
    if request.GET.get('hasta'):
        gestiones = gestiones.filter(fecha__lte=request.GET['hasta'])
    gestiones, total_encontrados, pagination_query, sort, direction = paginate_queryset(
        request, gestiones, default_ordering='fecha',
        allowed_ordering={'fecha': 'fecha', 'nombre': 'nombre'},
    )

    form = GestionAtencionForm()

    return render(request, 'FuncionarioApp/casos_sociales.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': _funcionario_sidebar_modules(),
        'gestiones': gestiones,
        'gestion_count': total_encontrados,
        'total_encontrados': total_encontrados,
        'pagination_query': pagination_query,
        'sort': sort,
        'direction': direction,
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

    nombre = (data.get('nombre') or '').strip() or None
    fecha = data.get('fecha')
    observaciones = data.get('observaciones', '').strip()

    if not fecha:
        return JsonResponse({'success': False, 'message': 'La fecha es un campo obligatorio.'}, status=400)

    try:
        with transaction.atomic():
            gestion = GestionAtencion.objects.create(
                nombre=nombre,
                fecha=fecha,
                observaciones=observaciones
            )
            registrar_historial(
                actor=request.user,
                action='Crear gestión social',
                entity=f'GestionAtencion:{gestion.pk}',
                after={'codigo': str(gestion.codigo), 'nombre': gestion.nombre, 'fecha': str(gestion.fecha)},
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
        'nombre': gestion.nombre or '',
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

    nombre = (data.get('nombre') or '').strip() or None
    fecha = data.get('fecha')
    observaciones = data.get('observaciones', '').strip()

    if not fecha:
        return JsonResponse({'success': False, 'message': 'Por favor ingresa una fecha válida.'}, status=400)

    try:
        with transaction.atomic():
            gestion.nombre = nombre
            gestion.fecha = fecha
            gestion.observaciones = observaciones
            gestion.save(update_fields=['nombre', 'fecha', 'observaciones'])

            registrar_historial(
                actor=request.user,
                action='Editar gestión social',
                entity=f'GestionAtencion:{gestion.pk}',
                after={'nombre': gestion.nombre, 'fecha': str(gestion.fecha), 'observaciones': gestion.observaciones},
            )

        return JsonResponse({'success': True, 'message': 'La gestión social se actualizó correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar: {str(e)}'}, status=500)


def _carta_snapshot(carta):
    return {
        'numero_carta': carta.numero_carta,
        'fecha': carta.fecha.isoformat() if carta.fecha else None,
        'remitente': carta.remitente,
        'destinatario': carta.destinatario,
        'telefono': carta.telefono,
        'materia': carta.materia,
        'fecha_respuesta': carta.fecha_respuesta.isoformat() if carta.fecha_respuesta else None,
        'responsable_seguimiento_id': carta.responsable_seguimiento_id,
        'area_derivada': carta.area_derivada,
        'pronunciamiento': carta.pronunciamiento,
        'observaciones': carta.observaciones,
        'documento_adjunto_id': carta.documento_adjunto_id,
        'fecha_cierre': carta.fecha_cierre.isoformat() if carta.fecha_cierre else None,
        'estado': carta.estado,
        'delegacion_id': carta.delegacion_id,
    }


@cargo_required('funcionario', 'delegado', permission='manage_letter_tube')
def tubo_cartas(request):
    delegation = active_delegation(request)
    is_delegado = getattr(getattr(request.user, 'cargo', None), 'nombre', '').strip().casefold().startswith('delegado')
    sgr_role = 'Delegación' if is_delegado else 'Funcionario'
    sidebar = (
        (
            {'label': 'Agenda colectiva', 'url_name': 'delegado:home'},
            {'label': 'Resumen de la delegación', 'url_name': 'delegado:resumen'},
            {'label': 'Tubo de Cartas', 'url_name': 'funcionario:tubo_cartas'},
        )
        if is_delegado
        else _funcionario_sidebar_modules()
    )

    cartas_qs = Carta.objects.none()
    if delegation:
        cartas_qs = Carta.objects.filter(delegacion=delegation).select_related(
            'responsable_seguimiento', 'autor', 'documento_adjunto', 'delegacion'
        )

    form = CartaForm(request.POST or None, request.FILES or None, delegation=delegation)
    if request.method == 'POST':
        if not delegation:
            messages.error(request, 'Tu cuenta no tiene una delegación activa asignada.')
            return redirect('funcionario:tubo_cartas')
        if form.is_valid():
            with transaction.atomic():
                carta = form.save(commit=False)
                carta.delegacion = delegation
                carta.autor = request.user
                archivo = form.cleaned_data.get('documento')
                if archivo:
                    evidencia_obj = Evidencia.objects.create(
                        archivo=archivo,
                    )
                    carta.documento_adjunto = evidencia_obj
                carta.save()
                registrar_historial(
                    actor=request.user,
                    action='Registrar carta en Tubo de Cartas',
                    entity=f'Carta:{carta.pk}',
                    after=_carta_snapshot(carta),
                )
            messages.success(request, f'Carta N° {carta.numero_carta} registrada correctamente.')
            return redirect('funcionario:tubo_cartas')
        else:
            messages.error(request, 'Revisa los campos obligatorios del formulario.')

    estado_filtro = request.GET.get('estado', '').strip()
    if estado_filtro:
        cartas_qs = cartas_qs.filter(estado=estado_filtro)
    if request.GET.get('q'):
        cartas_qs = cartas_qs.filter(Q(numero_carta__icontains=request.GET['q']) | Q(remitente__icontains=request.GET['q']) | Q(destinatario__icontains=request.GET['q']) | Q(materia__icontains=request.GET['q']))
    if request.GET.get('responsable'):
        cartas_qs = cartas_qs.filter(responsable_seguimiento_id=request.GET['responsable'])
    if request.GET.get('desde'):
        cartas_qs = cartas_qs.filter(fecha__gte=request.GET['desde'])
    if request.GET.get('hasta'):
        cartas_qs = cartas_qs.filter(fecha__lte=request.GET['hasta'])

    if request.GET.get('export') == 'csv':
        from AdminApp.csv_utils import csv_response
        rows = [[
            'N° Carta', 'Fecha', 'Remitente', 'Destinatario', 'Materia',
            'Responsable', 'Área derivada', 'Estado', 'Fecha respuesta', 'Fecha cierre',
        ]]
        rows.extend([
            c.numero_carta,
            c.fecha.strftime('%d/%m/%Y') if c.fecha else '',
            c.remitente,
            c.destinatario,
            c.materia,
            (c.responsable_seguimiento.get_full_name() or c.responsable_seguimiento.email) if c.responsable_seguimiento else '',
            c.area_derivada or '',
            c.get_estado_display(),
            c.fecha_respuesta.strftime('%d/%m/%Y') if c.fecha_respuesta else '',
            c.fecha_cierre.strftime('%d/%m/%Y') if c.fecha_cierre else '',
        ] for c in cartas_qs)
        return csv_response(
            request,
            filename='tubo_cartas.csv',
            rows=rows,
            entity='TuboCartas',
            action='Exportar Tubo de Cartas CSV',
            title='Reporte de Tubo de Cartas',
            delegation=delegation,
            filters={'estado': estado_filtro},
            row_count=cartas_qs.count(),
        )

    cartas_qs, total_encontrados, pagination_query, sort, direction = paginate_queryset(
        request, cartas_qs, default_ordering='fecha',
        allowed_ordering={'fecha': 'fecha', 'estado': 'estado', 'responsable': 'responsable_seguimiento__email'},
    )

    return render(request, 'FuncionarioApp/tubo_cartas.html', {
        'sgr_role': sgr_role,
        'sidebar_modules': sidebar,
        'form': form,
        'cartas': cartas_qs,
        'estados_choices': Carta.Estado.choices,
        'estado_filtro': estado_filtro,
        'responsables': form.fields['responsable_seguimiento'].queryset,
        'total_encontrados': total_encontrados,
        'pagination_query': pagination_query,
        'sort': sort,
        'direction': direction,
    })


@cargo_required('funcionario', 'delegado', permission='view_letter_detail')
@require_GET
def detalle_carta_json(request, carta_id):
    delegation = active_delegation(request)
    carta = get_object_or_404(Carta, pk=carta_id, delegacion=delegation)
    return JsonResponse({
        'id': carta.pk,
        'numero_carta': carta.numero_carta,
        'fecha': carta.fecha.strftime('%Y-%m-%d') if carta.fecha else '',
        'remitente': carta.remitente,
        'destinatario': carta.destinatario,
        'telefono': carta.telefono or '',
        'materia': carta.materia,
        'fecha_respuesta': carta.fecha_respuesta.strftime('%Y-%m-%d') if carta.fecha_respuesta else '',
        'responsable_seguimiento_id': carta.responsable_seguimiento_id,
        'area_derivada': carta.area_derivada or '',
        'pronunciamiento': carta.pronunciamiento or '',
        'observaciones': carta.observaciones or '',
        'fecha_cierre': carta.fecha_cierre.strftime('%Y-%m-%d') if carta.fecha_cierre else '',
        'estado': carta.estado,
        'documento_url': carta.documento_adjunto.archivo.url if carta.documento_adjunto and carta.documento_adjunto.archivo else None,
    })


@cargo_required('funcionario', 'delegado', permission='edit_letter_ajax')
@require_POST
def editar_carta_ajax(request, carta_id):
    delegation = active_delegation(request)
    carta = get_object_or_404(Carta, pk=carta_id, delegacion=delegation)
    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)
        if 'responsable_seguimiento_id' in payload and 'responsable_seguimiento' not in payload:
            payload['responsable_seguimiento'] = payload['responsable_seguimiento_id']
        files = None
    else:
        payload = request.POST
        files = request.FILES or None

    form = CartaForm(data=payload, files=files, instance=carta, delegation=delegation)
    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'message': 'Revisa los datos de la carta.',
            'errors': form.errors.get_json_data(),
        }, status=400)

    before = _carta_snapshot(carta)
    try:
        with transaction.atomic():
            carta = form.save(commit=False)
            archivo = form.cleaned_data.get('documento')
            if archivo:
                carta.documento_adjunto = Evidencia.objects.create(archivo=archivo)
            carta.save()

            registrar_historial(
                actor=request.user,
                action='Actualizar carta en Tubo de Cartas',
                entity=f'Carta:{carta.pk}',
                before=before,
                after=_carta_snapshot(carta),
            )
        return JsonResponse({'success': True, 'message': 'La carta fue actualizada correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar: {str(e)}'}, status=500)


@cargo_required('funcionario', permission='view_vecino_juntas_by_delegation')
@require_GET
def juntas_por_delegacion_vecino(request, delegacion_id):
    """Retorna juntas de vecinos asociadas a la delegación seleccionada."""
    juntas = list(
        JuntaVecino.objects.filter(delegacion_id=delegacion_id)
        .order_by('nombre')
        .values('pk', 'nombre', 'numero_rpj')
    )
    return JsonResponse({'juntas': juntas})


@cargo_required('funcionario', permission='view_vecino_cargos_by_junta')
@require_GET
def cargos_por_junta_vecino(request, junta_id):
    """Retorna cargos JV asociados a la junta de vecinos seleccionada."""
    cargos = list(
        CargoJv.objects.filter(junta_vecino_id=junta_id)
        .order_by('nombre')
        .values('pk', 'nombre', 'permisos')
    )
    return JsonResponse({'cargos': cargos})


@cargo_required('funcionario', permission='view_vecino_territorios_by_delegation')
@require_GET
def territorios_por_delegacion_vecino(request, delegacion_id):
    """Retorna los territorios asociados a la delegación seleccionada."""
    territorios = list(
        Territorio.objects.filter(delegacion_id=delegacion_id)
        .order_by('nombre')
        .values('pk', 'nombre')
    )
    return JsonResponse({'territorios': territorios})

### Gestión de Territorios
def _territorio_snapshot(territorio):
    return {
        'nombre': territorio.nombre,
        'delegacion_id': territorio.delegacion_id,
    }

@cargo_required('admin', 'administrador', permission='access_admin_territories')
def territorios(request):
    """Vista principal para listar, buscar y crear territorios en el panel de administración."""
    query = request.GET.get('q', '').strip()
    delegacion_filtro = request.GET.get('delegacion', '').strip()

    queryset = Territorio.objects.select_related('delegacion').all().order_by('delegacion__nombre', 'nombre')

    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query) | Q(delegacion__nombre__icontains=query)
        )
    if delegacion_filtro.isdecimal():
        queryset = queryset.filter(delegacion_id=int(delegacion_filtro))

    form = TerritorioForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            nombre = form.cleaned_data['nombre']
            delegacion = form.cleaned_data['delegacion']
            if Territorio.objects.filter(nombre__iexact=nombre, delegacion=delegacion).exists():
                messages.error(request, f'Ya existe el territorio "{nombre}" en la delegación {delegacion.nombre}.')
            else:
                with transaction.atomic():
                    territorio = form.save()
                    registrar_historial(
                        actor=request.user,
                        action='Crear territorio',
                        entity=f'Territorio:{territorio.pk}',
                        after=_territorio_snapshot(territorio),
                    )
                messages.success(request, 'Territorio creado correctamente.')
                return redirect('administracion:territorios')
        else:
            messages.error(request, 'Revisa los campos obligatorios del formulario.')

    page_obj = Paginator(queryset, 20).get_page(request.GET.get('page'))
    delegaciones = Delegacion.objects.filter(estado=Delegacion.Estado.ACTIVADO).order_by('nombre')

    return render(request, 'AdminApp/territorios.html', {
        'sgr_role': 'Administración',
        'sidebar_modules': _admin_dashboard_modules(request.user),
        'form': form,
        'page_obj': page_obj,
        'delegaciones': delegaciones,
        'search_query': query,
        'delegacion_filtro': delegacion_filtro,
    })

@cargo_required('admin', 'administrador', permission='search_admin_territories_ajax')
@require_GET
def buscar_territorios_ajax(request):
    """Endpoint AJAX (keyup) para filtrar territorios dinámicamente."""
    query = request.GET.get('q', '').strip()
    delegacion_filtro = request.GET.get('delegacion', '').strip()

    queryset = Territorio.objects.select_related('delegacion').all().order_by('delegacion__nombre', 'nombre')
    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query) | Q(delegacion__nombre__icontains=query)
        )
    if delegacion_filtro.isdecimal():
        queryset = queryset.filter(delegacion_id=int(delegacion_filtro))

    resultados = [
        {
            'id': t.pk,
            'nombre': t.nombre,
            'delegacion_id': t.delegacion_id,
            'delegacion_nombre': t.delegacion.nombre if t.delegacion else '—',
        }
        for t in queryset[:50]
    ]
    return JsonResponse({'success': True, 'territorios': resultados})


@cargo_required('admin', 'administrador', permission='view_admin_territories_detail')
@require_GET
def detalle_territorio_json(request, territorio_id):
    """Devuelve los datos del territorio en JSON para precargar el modal de edición."""
    territorio = get_object_or_404(Territorio, pk=territorio_id)
    return JsonResponse({
        'id': territorio.pk,
        'nombre': territorio.nombre,
        'delegacion_id': territorio.delegacion_id,
    })


@cargo_required('admin', 'administrador', permission='edit_admin_territories_ajax')
@require_POST
def editar_territorio_ajax(request, territorio_id):
    """Actualiza el territorio vía AJAX y registra en Historial."""
    territorio = get_object_or_404(Territorio, pk=territorio_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Payload JSON inválido.'}, status=400)

    nombre = data.get('nombre', '').strip()
    delegacion_id = data.get('delegacion_id')

    if not nombre or not delegacion_id:
        return JsonResponse({'success': False, 'message': 'El nombre y la delegación son obligatorios.'}, status=400)

    if Territorio.objects.filter(nombre__iexact=nombre, delegacion_id=delegacion_id).exclude(pk=territorio.pk).exists():
        return JsonResponse({'success': False, 'message': f'Ya existe otro territorio "{nombre}" en esa delegación.'}, status=400)

    before = _territorio_snapshot(territorio)
    try:
        with transaction.atomic():
            territorio.nombre = nombre
            territorio.delegacion_id = delegacion_id
            territorio.save()

            registrar_historial(
                actor=request.user,
                action='Editar territorio AJAX',
                entity=f'Territorio:{territorio.pk}',
                before=before,
                after=_territorio_snapshot(territorio),
            )
        return JsonResponse({'success': True, 'message': 'El territorio fue actualizado correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al actualizar el territorio: {str(e)}'}, status=500)


@cargo_required('admin', 'administrador', permission='delete_admin_territories')
@require_POST
def eliminar_territorio(request, territorio_id):
    """Elimina un territorio si no tiene registros protegidos asociados."""
    territorio = get_object_or_404(Territorio, pk=territorio_id)
    before = _territorio_snapshot(territorio)
    entity = f'Territorio:{territorio.pk}'
    try:
        with transaction.atomic():
            territorio.delete()
            registrar_historial(
                actor=request.user,
                action='Eliminar territorio',
                entity=entity,
                before=before,
            )
        messages.success(request, 'Territorio eliminado correctamente.')
    except ProtectedError:
        messages.error(request, 'No se puede eliminar el territorio porque tiene vecinos, juntas o compromisos asociados.')
    return redirect('administracion:territorios')

