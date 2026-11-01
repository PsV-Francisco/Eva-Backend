from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from AdminApp.audit import registrar_historial
from AdminApp.models import Delegacion, SubAtencion
from config.decorators import cargo_required
from config.delegations import active_delegation
from CoordinadorApp.models import Desempeno, Periodo
from CoordinadorApp.services import clasificar_umbral, resumen_cumplimiento, umbral_delegacion
from DelegadoApp.models import Agenda, Compromiso
from DelegadoApp.forms import CompromisoEstadoForm
from DelegadoApp.services import actualizar_estado_compromiso
from FuncionarioApp.forms import (
	CasoSocialForm,
	CompromisoEvidenciaForm,
	FuncionarioCompromisoForm,
	GestionAtencionForm,
	JuntaVecinosForm,
	RegistroForm,
	VecinoForm,
)
from FuncionarioApp.models import (
    AtencionSocial,
    CasoSocial,
    GestionAtencion,
    JuntaVecinos,
    Registro,
    Solicitante,
    Vecino,
    VecinoJunta,
    normalizar_telefono,
)
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


def _cases_for_user(user, delegation):
    cases = CasoSocial.objects.filter(
        atencion_social__usuario=user,
    )
    if delegation is None:
        return cases.none()
    return cases.filter(
        Q(atencion_social__delegacion=delegation)
        | Q(
            atencion_social__delegacion__isnull=True,
            atencion_social__usuario__delegacion=delegation,
        )
    )


@cargo_required('funcionario', permission='access_employee_dashboard')
def home(request):
    return _render_cumplimiento(request)


@cargo_required('funcionario', permission='manage_employee_activities')
def gestion_actividades(request):
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
                return redirect('funcionario:gestion_actividades')
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
            return redirect('funcionario:gestion_actividades')

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
            return redirect('funcionario:gestion_actividades')
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
            {'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
            {'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
            {'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
            {'label': 'Gestión de Juntas de Vecinos', 'url_name': 'funcionario:juntas'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Gestión de Compromisos', 'url_name': 'funcionario:agenda_colectiva'},
        ),
        'registro_count': registros.count(),
    })


def _render_cumplimiento(request):
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
    has_items = bool(summary['items'])
    return render(request, 'FuncionarioApp/cumplimiento.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
            {'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
            {'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
            {'label': 'Gestión de Juntas de Vecinos', 'url_name': 'funcionario:juntas'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Gestión de Compromisos', 'url_name': 'funcionario:agenda_colectiva'},
        ),
        'periodos': assigned_periods,
        'periodo_seleccionado': period,
        'summary': summary,
        'item_count': len(summary['items']),
        'umbral_delegacion': umbral_delegacion(),
        'clasificacion_umbral': clasificar_umbral(
            summary['avance_real'],
            tiene_items=has_items,
        ),
    })


@cargo_required('funcionario', permission='manage_employee_compliance')
def cumplimiento(request):
    return redirect('funcionario:home')


def _funcionario_sidebar_modules():
	return (
		{'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
		{'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
		{'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
		{'label': 'Gestión de Juntas de Vecinos', 'url_name': 'funcionario:juntas'},
		{'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
		{'label': 'Gestión de Compromisos', 'url_name': 'funcionario:agenda_colectiva'},
	)


def _es_administrador(user):
	cargo = getattr(user, 'cargo', None)
	return bool(cargo and cargo.nombre.strip().casefold() in {'admin', 'administrador'})


def _vecinos_para_usuario(request):
	user = request.user
	queryset = Vecino.objects.select_related('delegacion', 'solicitante')
	if _es_administrador(user):
		return queryset
	delegation = active_delegation(request)
	if delegation is None:
		return queryset.none()
	return queryset.filter(delegacion=delegation)


def _delegaciones_para_vecino(request):
	if _es_administrador(request.user):
		return Delegacion.objects.filter(
			estado=Delegacion.Estado.ACTIVA,
		).order_by('nombre')
	delegation = active_delegation(request)
	return Delegacion.objects.filter(pk=delegation.pk) if delegation else Delegacion.objects.none()


def _vecino_snapshot(vecino):
	return {
		'nombre': vecino.nombre,
		'telefono': vecino.telefono,
		'direccion': vecino.direccion,
		'territorio': vecino.territorio,
		'delegacion_id': vecino.delegacion_id,
		'solicitante_id': vecino.solicitante_id,
		'activo': vecino.activo,
	}


def _telefono_repetido(vecino):
	phone = normalizar_telefono(vecino.telefono)
	return any(
		normalizar_telefono(value) == phone
		for value in Vecino.objects.filter(
			delegacion_id=vecino.delegacion_id,
		).exclude(pk=vecino.pk).values_list('telefono', flat=True)
	)


def _juntas_para_usuario(request):
	queryset = JuntaVecinos.objects.select_related('delegacion')
	if _es_administrador(request.user):
		return queryset
	delegation = active_delegation(request)
	if delegation is None:
		return queryset.none()
	return queryset.filter(delegacion=delegation)


def _delegaciones_para_junta(request):
	if _es_administrador(request.user):
		return Delegacion.objects.filter(
			estado=Delegacion.Estado.ACTIVA,
		).order_by('nombre')
	delegation = active_delegation(request)
	return Delegacion.objects.filter(pk=delegation.pk) if delegation else Delegacion.objects.none()


def _junta_snapshot(junta):
	return {
		'nombre': junta.nombre,
		'domicilio_legal': junta.domicilio_legal,
		'territorio': junta.territorio,
		'delegacion_id': junta.delegacion_id,
		'cantidad_socios_activos': junta.cantidad_socios_activos,
		'fecha_constitucion': junta.fecha_constitucion.isoformat(),
		'numero_personalidad_juridica': junta.numero_personalidad_juridica,
		'fecha_inscripcion': junta.fecha_inscripcion.isoformat(),
		'numero_registro': junta.numero_registro,
		'activo': junta.activo,
	}


def _personalidad_repetida(junta):
	return JuntaVecinos.objects.filter(
		numero_personalidad_juridica__iexact=junta.numero_personalidad_juridica,
	).exclude(pk=junta.pk).exists()


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
			| Q(territorio__icontains=search_query)
		).distinct()
	page_obj = Paginator(queryset.order_by('nombre', 'pk'), 20).get_page(
		request.GET.get('page'),
	)
	territorios = (
		_vecinos_para_usuario(request)
		.exclude(territorio='')
		.values_list('territorio', flat=True)
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


def _vecino_form(request, vecino_id=None):
	queryset = _vecinos_para_usuario(request)
	vecino = get_object_or_404(queryset, pk=vecino_id) if vecino_id else None
	delegaciones = _delegaciones_para_vecino(request)
	form = VecinoForm(
		request.POST or None,
		instance=vecino,
		delegaciones=delegaciones,
	)
	if request.method == 'POST' and form.is_valid():
		before = _vecino_snapshot(vecino) if vecino else None
		membership_count = VecinoJunta.objects.filter(vecino=vecino).count() if vecino else 0
		try:
			with transaction.atomic():
				vecino = form.save()
				selected_junta = form.cleaned_data.get('junta')
				displayed_membership = form.displayed_membership
				if selected_junta:
					if displayed_membership:
						displayed_membership.junta = selected_junta
						displayed_membership.es_dirigente = form.cleaned_data.get('es_dirigente', False)
						displayed_membership.save(update_fields=['junta', 'es_dirigente', 'actualizado'])
					else:
						VecinoJunta.objects.create(
							vecino=vecino,
							junta=selected_junta,
							es_dirigente=form.cleaned_data.get('es_dirigente', False),
						)
				elif displayed_membership:
					displayed_membership.delete()
				registrar_historial(
					actor=request.user,
					action='Editar vecino' if before else 'Crear vecino',
					entity=f'Vecino:{vecino.pk}',
					before=before,
					after={
						**_vecino_snapshot(vecino),
						'junta_id': selected_junta.pk if selected_junta else None,
						'es_dirigente': form.cleaned_data.get('es_dirigente', False),
					},
				)
		except IntegrityError:
			form.add_error('junta', 'El vecino ya está relacionado con esa junta.')
		else:
			if membership_count > 1:
				messages.warning(request, 'Aviso: se modificó solo la relación de junta mostrada; las demás se conservaron.')
			if _telefono_repetido(vecino):
				messages.warning(request, 'Advertencia: ya existe otro vecino con ese teléfono en la delegación.')
			messages.success(request, 'Vecino actualizado correctamente.' if before else 'Vecino creado correctamente.')
			return redirect('funcionario:vecinos')
	return render(request, 'FuncionarioApp/vecino_form.html', {
		'sgr_role': 'Funcionario',
		'sidebar_modules': _funcionario_sidebar_modules(),
		'form': form,
		'vecino': vecino,
		'territorios': _vecinos_para_usuario(request).exclude(
			territorio='',
		).values_list('territorio', flat=True).distinct().order_by('territorio'),
	})


@cargo_required('funcionario', permission='access_funcionario_juntas')
def juntas(request):
	queryset = _juntas_para_usuario(request)
	search_query = request.GET.get('q', '').strip()
	show_inactive = request.GET.get('inactivos') == '1'
	if not show_inactive:
		queryset = queryset.filter(activo=True)
	if search_query:
		queryset = queryset.filter(
			Q(nombre__icontains=search_query)
			| Q(domicilio_legal__icontains=search_query)
			| Q(territorio__icontains=search_query)
			| Q(numero_personalidad_juridica__icontains=search_query)
			| Q(numero_registro__icontains=search_query)
		).distinct()
	page_obj = Paginator(queryset.order_by('nombre', 'pk'), 20).get_page(
		request.GET.get('page'),
	)
	return render(request, 'FuncionarioApp/juntas.html', {
		'sgr_role': 'Funcionario',
		'sidebar_modules': _funcionario_sidebar_modules(),
		'page_obj': page_obj,
		'search_query': search_query,
		'show_inactive': show_inactive,
	})


def _junta_form(request, junta_id=None):
	queryset = _juntas_para_usuario(request)
	junta = get_object_or_404(queryset, pk=junta_id) if junta_id else None
	form = JuntaVecinosForm(
		request.POST or None,
		instance=junta,
		delegaciones=_delegaciones_para_junta(request),
	)
	if request.method == 'POST' and form.is_valid():
		before = _junta_snapshot(junta) if junta else None
		junta = form.save()
		registrar_historial(
			actor=request.user,
			action='Editar junta de vecinos' if before else 'Crear junta de vecinos',
			entity=f'JuntaVecinos:{junta.pk}',
			before=before,
			after=_junta_snapshot(junta),
		)
		if _personalidad_repetida(junta):
			messages.warning(request, 'Advertencia: ya existe otra junta con ese número de personalidad jurídica.')
		messages.success(request, 'Junta actualizada correctamente.' if before else 'Junta creada correctamente.')
		return redirect('funcionario:juntas')
	return render(request, 'FuncionarioApp/junta_form.html', {
		'sgr_role': 'Funcionario',
		'sidebar_modules': _funcionario_sidebar_modules(),
		'form': form,
		'junta': junta,
		'territorios': _juntas_para_usuario(request).exclude(
			territorio='',
		).values_list('territorio', flat=True).distinct().order_by('territorio'),
	})


@cargo_required('admin', 'administrador', permission='create_juntas')
def junta_form(request):
	return _junta_form(request)


@cargo_required('funcionario', permission='edit_juntas')
def editar_junta(request, junta_id):
	return _junta_form(request, junta_id)


@cargo_required('funcionario', permission='deactivate_juntas')
def desactivar_junta(request, junta_id):
	junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
	if request.method == 'POST':
		before = _junta_snapshot(junta)
		junta.activo = False
		with transaction.atomic():
			junta.save(update_fields=['activo', 'actualizado'])
			registrar_historial(
				actor=request.user,
				action='Desactivar junta de vecinos',
				entity=f'JuntaVecinos:{junta.pk}',
				before=before,
				after=_junta_snapshot(junta),
			)
		messages.success(request, 'Junta desactivada correctamente.')
	return redirect('funcionario:juntas')


@cargo_required('funcionario', permission='delete_juntas')
def eliminar_junta(request, junta_id):
	junta = get_object_or_404(_juntas_para_usuario(request), pk=junta_id)
	if request.method == 'POST':
		before = _junta_snapshot(junta)
		try:
			with transaction.atomic():
				junta.delete()
				registrar_historial(
					actor=request.user,
					action='Eliminar junta de vecinos',
					entity=f'JuntaVecinos:{junta.pk}',
					before=before,
				)
		except ProtectedError:
			messages.error(request, 'No se puede eliminar la junta porque tiene vecinos relacionados. Desactívala en su lugar.')
		else:
			messages.success(request, 'Junta eliminada correctamente.')
	return redirect('funcionario:juntas')


@cargo_required('funcionario', permission='manage_vecinos')
def vecino_form(request):
	return _vecino_form(request)


@cargo_required('funcionario', permission='edit_vecinos')
def editar_vecino(request, vecino_id):
	return _vecino_form(request, vecino_id)


@cargo_required('funcionario', permission='deactivate_vecinos')
def desactivar_vecino(request, vecino_id):
	vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
	if request.method == 'POST':
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
def eliminar_vecino(request, vecino_id):
	vecino = get_object_or_404(_vecinos_para_usuario(request), pk=vecino_id)
	if request.method == 'POST':
		before = _vecino_snapshot(vecino)
		try:
			with transaction.atomic():
				vecino.delete()
				registrar_historial(
					actor=request.user,
					action='Eliminar vecino',
					entity=f'Vecino:{vecino.pk}',
					before=before,
				)
		except ProtectedError:
			messages.error(request, 'No se puede eliminar el vecino porque tiene registros asociados. Desactívalo en su lugar.')
		else:
			messages.success(request, 'Vecino eliminado correctamente.')
	return redirect('funcionario:vecinos')


@cargo_required('funcionario', permission='manage_social_care')
def atencion_social(request):
    delegation = active_delegation(request)
    case_form = CasoSocialForm(delegation=delegation)
    attention_form = GestionAtencionForm()
    selected_case = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'crear_caso':
            case_form = CasoSocialForm(request.POST, delegation=delegation)
            if delegation is None:
                messages.error(request, 'Selecciona una delegación autorizada antes de registrar una atención.')
            elif case_form.is_valid():
                with transaction.atomic():
                    case_record = case_form.save(commit=False)
                    case_record.usuario = request.user
                    case_record.solicitante = case_form.resolve_solicitante()
                    case_record.delegacion = delegation
                    case_record.tipo_atencion_catalogo = case_form.cleaned_data[
                        'tipo_atencion_catalogo'
                    ]
                    case_record.sub_atencion = case_form.cleaned_data['sub_atencion']
                    case_record.tipo_atencion = case_record.tipo_atencion_catalogo.nombre
                    case_record.descripcion = case_form.cleaned_data['descripcion'].strip()
                    case_record.fecha = timezone.localdate()
                    case_record.full_clean()
                    case_record.save()
                    case = CasoSocial.objects.create(atencion_social=case_record)
                    registrar_historial(
                        actor=request.user,
                        action='Crear caso social',
                        entity=f'CasoSocial:{case.pk}',
                        after={
                            'codigo': str(case.codigo),
                            'usuario_id': request.user.pk,
                            'delegacion_id': delegation.pk,
                            'solicitante_id': case_record.solicitante_id,
                            'tipo_atencion_id': case_record.tipo_atencion_catalogo_id,
                            'sub_atencion_id': case_record.sub_atencion_id,
                        },
                    )
                messages.success(request, f'Caso social creado: {case.codigo}.')
                return redirect('funcionario:atencion_social')
            messages.error(request, 'Revisa los datos del caso social.')
        elif action == 'agregar_atencion':
            case = get_object_or_404(
                _cases_for_user(request.user, delegation).select_related(
                    'atencion_social',
                ),
                pk=request.POST.get('caso_id'),
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

    cases = _cases_for_user(request.user, delegation).select_related(
        'atencion_social',
        'atencion_social__solicitante',
        'atencion_social__delegacion',
        'atencion_social__tipo_atencion_catalogo',
        'atencion_social__sub_atencion',
        'atencion_social__usuario',
    ).prefetch_related(
        'atencion_social__gestiones__evidencias',
    )
    return render(request, 'FuncionarioApp/atencion_social.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
            {'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
            {'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
            {'label': 'Gestión de Juntas de Vecinos', 'url_name': 'funcionario:juntas'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Gestión de Compromisos', 'url_name': 'funcionario:agenda_colectiva'},
        ),
        'case_form': case_form,
        'attention_form': attention_form,
        'cases': cases,
        'case_count': cases.count(),
        'selected_case': selected_case,
        'active_delegation': delegation,
    })


@cargo_required('funcionario', permission='search_social_applicants')
@require_GET
def buscar_solicitantes(request):
    delegation = active_delegation(request)
    query = request.GET.get('q', '').strip()
    if delegation is None or len(query) < 2:
        return JsonResponse({'results': []})

    results = Solicitante.objects.filter(delegacion=delegation).filter(
        Q(identificador__icontains=query) | Q(nombre__icontains=query),
    ).order_by('nombre', 'identificador').values(
        'pk', 'identificador', 'nombre',
    )[:10]
    return JsonResponse({'results': list(results)})


@cargo_required('funcionario', permission='view_social_subattentions')
@require_GET
def subatenciones_tipo(request, tipo_id):
    subattentions = SubAtencion.objects.filter(
        tipo_atencion_id=tipo_id,
        tipo_atencion__estado='activo',
        estado=SubAtencion.Estado.ACTIVO,
    ).order_by('nombre').values('pk', 'nombre', 'codigo')
    return JsonResponse({'results': list(subattentions)})


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
    if delegation_id and selected_period:
        registros = Registro.objects.filter(
            Q(autor__delegacion_id=delegation_id)
            | Q(autor__delegaciones_autorizadas__pk=delegation_id),
            periodo=selected_period,
            incluir_en_agenda=True,
        ).select_related('autor', 'item').distinct().order_by('-fecha')
        commitments = Compromiso.objects.filter(
            agenda__delegacion_id=delegation_id,
            agenda__periodo=selected_period,
        ).select_related('agenda', 'agenda__periodo').prefetch_related(
            'responsables', 'evidencias_compromiso',
        )
    return render(request, 'FuncionarioApp/agenda_colectiva.html', {
        'sgr_role': 'Funcionario',
        'sidebar_modules': (
            {'label': 'Tablero Personal', 'url_name': 'funcionario:home'},
            {'label': 'Gestión de Actividades', 'url_name': 'funcionario:gestion_actividades'},
            {'label': 'Gestión de Vecinos', 'url_name': 'funcionario:vecinos'},
            {'label': 'Gestión de Juntas de Vecinos', 'url_name': 'funcionario:juntas'},
            {'label': 'Atención social', 'url_name': 'funcionario:atencion_social'},
            {'label': 'Gestión de Compromisos', 'url_name': 'funcionario:agenda_colectiva'},
        ),
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
	}


def _compromisos_responsable(request):
	delegation = active_delegation(request)
	if delegation is None:
		return delegation, Compromiso.objects.none()
	return delegation, Compromiso.objects.filter(
		agenda__delegacion=delegation,
		responsables=request.user,
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
				commitment.responsables.add(request.user)
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
				'observaciones', 'actualizado',
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
