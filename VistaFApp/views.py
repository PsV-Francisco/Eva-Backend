from django.db.models import F, Q, Sum
from django.shortcuts import render

from AdminApp.models import Usuario
from CoordinadorApp.models import Desempeno, Periodo
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import Registro
from SupervisorApp.models import Evidencia
from config.decorators import cargo_required
from config.delegations import active_delegation


@cargo_required(
    'vistaf',
    'consulta',
    'usuario de consulta',
    permission='view_public_reports',
)
def home(request):
	registros = Registro.objects.all()
	compromisos = Compromiso.objects.all()
	evidencias = Evidencia.objects.filter(estado=Evidencia.Estado.PENDIENTE)
	desempenos = Desempeno.objects.all()
	query = request.GET.get('q', '').strip()
	delegation = active_delegation(request)

	if delegation:
		delegation_id = delegation.pk
		registros = registros.filter(
			autor__usuariodelegacion__delegacion_id=delegation_id,
			autor__usuariodelegacion__fecha_fin__isnull=True,
		).distinct()
		compromisos = compromisos.filter(agenda__delegacion_id=delegation_id)
		evidencias = evidencias.filter(
			Q(
				registros__autor__usuariodelegacion__delegacion_id=delegation_id,
				registros__autor__usuariodelegacion__fecha_fin__isnull=True,
			)
			| Q(compromisos__agenda__delegacion_id=delegation_id)
			| Q(
				atenciones_sociales__autor__usuariodelegacion__delegacion_id=delegation_id,
				atenciones_sociales__autor__usuariodelegacion__fecha_fin__isnull=True,
			)
		).distinct()
		desempenos = desempenos.filter(
			usuario__usuariodelegacion__delegacion_id=delegation_id,
			usuario__usuariodelegacion__fecha_fin__isnull=True,
		).distinct()
		scope_label = delegation.nombre
	elif request.user.is_superuser:
		scope_label = 'Visión general'
	else:
		registros = registros.none()
		compromisos = compromisos.none()
		evidencias = evidencias.none()
		desempenos = desempenos.none()
		scope_label = 'Sin delegación asignada'

	if query:
		desempenos = desempenos.filter(
			Q(usuario__email__icontains=query)
			| Q(usuario__first_name__icontains=query)
			| Q(usuario__last_name__icontains=query)
			| Q(item__nombre__icontains=query)
			| Q(periodo__nombre__icontains=query)
		)

	# Mismo filtro (un solo JOIN): sin esto, un funcionario con dos delegaciones
	# mostraba filas de otra delegación fuera del alcance del usuario.
	summary_filter = {'usuario__usuariodelegacion__fecha_fin__isnull': True}
	if delegation:
		summary_filter['usuario__usuariodelegacion__delegacion_id'] = delegation.pk
	summary = desempenos.filter(**summary_filter).values(
		delegacion=F('usuario__usuariodelegacion__delegacion__nombre'),
		periodo_nombre=F('periodo__nombre'),
	).annotate(meta_total=Sum('meta'), avance_total=Sum('avance')).order_by(
		'delegacion', 'periodo_nombre',
	)[:30]
	return render(request, 'VistaFApp/index.html', {
		'sgr_role': 'Consulta',
		'scope_label': scope_label,
		'query': query,
		'sidebar_modules': ('Búsqueda de información',),
		'registro_count': registros.count(),
		'compromiso_count': compromisos.count(),
		'evidencia_count': evidencias.count(),
		'periodo_count': Periodo.objects.filter(estado=Periodo.Estado.ABIERTO).count(),
		'summary': summary,
	})
