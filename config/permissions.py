from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDefinition:
    module: str
    codename: str
    label: str
    view_name: str
    cargos: tuple[str, ...]
    route_kwargs: tuple[tuple[str, object], ...] = ()
    show_in_menu: bool = True


PERMISSION_CATALOG = (
    PermissionDefinition('Coordinador', 'view_coordinator_reports', 'Consultar informes consolidados', 'coordinador:informes', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'view_coordinator_trends', 'Consultar tendencias históricas de cumplimiento', 'coordinador:tendencias', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'request_closed_period_authorization', 'Solicitar autorización para modificar períodos cerrados', 'coordinador:solicitudes_autorizacion', ('coordinador', 'admin', 'administrador')),
    
    PermissionDefinition('Administración', 'review_closed_period_authorizations', 'Resolver solicitudes de autorización de períodos cerrados', 'administracion:solicitudes-autorizacion', ('admin', 'administrador')),
    
    PermissionDefinition('Coordinador', 'manage_coordinator_goals', 'Administrar metas desde Coordinación', 'coordinador:metas', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'manage_coordinator_position_functions', 'Asignar funciones a cargos desde Coordinación', 'coordinador:cargos_funciones', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'view_coordinator_weights', 'Consultar ponderaciones por cargo o funcionario', 'coordinador:ponderaciones', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'manage_coordinator_periods', 'Administrar períodos del Coordinador', 'coordinador:periodos', ('coordinador', 'admin', 'administrador')),
    
    PermissionDefinition('Administración', 'access_admin_dashboard', 'Consultar panel de inicio de Administración', 'administracion:dashboard', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'access_admin_users', 'Administrar usuarios', 'administracion:home', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_parameters', 'Administrar parámetros del sistema', 'administracion:parametros', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_delegations', 'Administrar delegaciones', 'administracion:delegaciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_positions', 'Administrar cargos', 'administracion:cargos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_functions', 'Administrar funciones', 'administracion:funciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_position_functions', 'Administrar cargos por función', 'administracion:cargos-funciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_roles', 'Administrar roles y permisos', 'administracion:roles', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_items', 'Administrar ítems', 'administracion:items', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_attention_types', 'Administrar tipos de atención', 'administracion:tipos-atencion', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_subattentions', 'Administrar subatenciones', 'administracion:subatenciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_goals', 'Administrar metas', 'administracion:metas', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_history', 'Consultar historial', 'administracion:historial', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_password_audit', 'Consultar auditoría de recuperación', 'administracion:auditoria-recuperacion', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_absences', 'Consultar ausencias', 'administracion:ausencias', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_congratulations', 'Consultar felicitaciones', 'administracion:felicitaciones', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_complaints', 'Consultar reclamos', 'administracion:reclamos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_milestones', 'Consultar hitos', 'administracion:hitos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_neighbors', 'Administrar vecinos', 'administracion:vecinos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_neighborhood_associations', 'Administrar juntas de vecinos', 'administracion:juntas', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_generated_reports', 'Consultar informes generados', 'administracion:informes-generados', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_delegation_summary', 'Consultar resumen de delegaciones', 'administracion:resumen-delegacion', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_records', 'Consultar registros por delegación', 'administracion:registros', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_social_attentions', 'Consultar atenciones sociales por delegación', 'administracion:atenciones-sociales', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'access_admin_commitments', 'Consultar compromisos por delegación', 'administracion:compromisos', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'manage_admin_goal_adjustments', 'Ajustar metas de desempeño', 'administracion:ajustes-metas', ('admin', 'administrador')),
    
    # Beneficiados / Solicitantes (AdminApp)
    PermissionDefinition('Administración', 'access_admin_beneficiados', 'Consultar beneficiados', 'administracion:beneficiados', ('admin', 'administrador')),
    PermissionDefinition('Administración', 'create_admin_beneficiados', 'Crear beneficiados por AJAX', 'administracion:crear_beneficiado_ajax', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'view_admin_beneficiados_detail', 'Consultar detalle de beneficiado', 'administracion:detalle_beneficiado_json', ('admin', 'administrador'), (('beneficiado_id', 1),), False),
    PermissionDefinition('Administración', 'edit_admin_beneficiados', 'Editar beneficiados por AJAX', 'administracion:editar_beneficiado_ajax', ('admin', 'administrador'), (('beneficiado_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_beneficiados', 'Eliminar beneficiados', 'administracion:eliminar_beneficiado', ('admin', 'administrador'), (('beneficiado_id', 1),), False),

    PermissionDefinition('Administración', 'create_admin_absences', 'Crear ausencias', 'administracion:ausencia-nueva', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_absences', 'Modificar ausencias', 'administracion:ausencia-editar', ('admin', 'administrador'), (('ausencia_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_absences', 'Eliminar ausencias', 'administracion:ausencia-eliminar', ('admin', 'administrador'), (('ausencia_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_congratulations', 'Crear felicitaciones', 'administracion:felicitacion-nueva', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_congratulations', 'Modificar felicitaciones', 'administracion:felicitacion-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_congratulations', 'Eliminar felicitaciones', 'administracion:felicitacion-eliminar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_complaints', 'Crear reclamos', 'administracion:reclamo-nuevo', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_complaints', 'Modificar reclamos', 'administracion:reclamo-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_complaints', 'Eliminar reclamos', 'administracion:reclamo-eliminar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_milestones', 'Crear hitos', 'administracion:hito-nuevo', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_milestones', 'Modificar hitos', 'administracion:hito-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_milestones', 'Eliminar hitos', 'administracion:hito-eliminar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_records', 'Crear registros administrativos', 'administracion:registro-nuevo', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_records', 'Modificar registros administrativos', 'administracion:registro-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_social_attentions', 'Crear atenciones sociales administrativas', 'administracion:atencion-social-nueva', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_social_attentions', 'Modificar atenciones sociales administrativas', 'administracion:atencion-social-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_commitments', 'Crear compromisos administrativos', 'administracion:compromiso-nuevo', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_commitments', 'Modificar compromisos administrativos', 'administracion:compromiso-editar', ('admin', 'administrador'), (('record_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_neighbors', 'Crear vecinos', 'administracion:vecino-nuevo', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_neighbors', 'Modificar vecinos', 'administracion:vecino-editar', ('admin', 'administrador'), (('vecino_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_neighbors', 'Eliminar vecinos', 'administracion:vecino-eliminar', ('admin', 'administrador'), (('vecino_id', 1),), False),
    PermissionDefinition('Administración', 'create_admin_juntas', 'Crear juntas de vecinos', 'administracion:junta-nueva', ('admin', 'administrador'), show_in_menu=False),
    PermissionDefinition('Administración', 'edit_admin_juntas', 'Modificar juntas de vecinos', 'administracion:junta-editar', ('admin', 'administrador'), (('junta_id', 1),), False),
    PermissionDefinition('Administración', 'delete_admin_juntas', 'Eliminar juntas de vecinos', 'administracion:junta-eliminar', ('admin', 'administrador'), (('junta_id', 1),), False),
    
    # Permisos de FuncionarioApp
PermissionDefinition('Funcionario', 'access_employee_dashboard', 'Consultar registro de actividades', 'funcionario:home', ('funcionario',)),
    PermissionDefinition('Funcionario', 'manage_employee_activities', 'Gestionar actividades', 'funcionario:gestion_actividades', ('funcionario',)),
    PermissionDefinition('Funcionario', 'view_employee_record_detail', 'Consultar detalle JSON de actividad', 'funcionario:detalle_registro_json', ('funcionario',), (('registro_id', 1),), False),
    PermissionDefinition('Funcionario', 'edit_employee_record_ajax', 'Editar actividad por AJAX', 'funcionario:editar_registro_ajax', ('funcionario',), (('registro_id', 1),), False),
    
    PermissionDefinition('Funcionario', 'access_funcionario_vecinos', 'Consultar vecinos', 'funcionario:vecinos', ('funcionario',)),
    PermissionDefinition('Funcionario', 'manage_vecinos', 'Gestionar vecinos', 'funcionario:vecino_form', ('funcionario',), (), False),
    PermissionDefinition('Funcionario', 'edit_vecinos', 'Modificar vecinos', 'funcionario:editar_vecino', ('funcionario',), (('vecino_id', 1),), False),
    PermissionDefinition('Funcionario', 'view_vecino_detail', 'Consultar detalle JSON de vecino', 'funcionario:detalle_vecino_json', ('funcionario',), (('vecino_id', 1),), False),
    PermissionDefinition('Funcionario', 'edit_vecino_ajax', 'Editar vecino por AJAX', 'funcionario:editar_vecino_ajax', ('funcionario',), (('vecino_id', 1),), False),
    PermissionDefinition('Funcionario', 'deactivate_vecinos', 'Desactivar vecinos', 'funcionario:vecino_desactivar', ('funcionario',), (('vecino_id', 1),), False),
    PermissionDefinition('Funcionario', 'delete_vecinos', 'Eliminar vecinos', 'funcionario:vecino_eliminar', ('funcionario',), (('vecino_id', 1),), False),
    
    PermissionDefinition('Funcionario', 'access_funcionario_juntas', 'Consultar juntas de vecinos', 'funcionario:juntas', ('funcionario',)),
    PermissionDefinition('Administración', 'create_juntas', 'Crear juntas de vecinos', 'funcionario:junta_form', ('admin', 'administrador'), (), False),
    PermissionDefinition('Funcionario', 'edit_juntas', 'Modificar juntas de vecinos', 'funcionario:editar_junta', ('funcionario',), (('junta_id', 1),), False),
    PermissionDefinition('Funcionario', 'view_junta_detail', 'Consultar detalle JSON de junta', 'funcionario:detalle_junta_json', ('funcionario',), (('junta_id', 1),), False),
    PermissionDefinition('Funcionario', 'edit_junta_ajax', 'Editar junta por AJAX', 'funcionario:editar_junta_ajax', ('funcionario',), (('junta_id', 1),), False),
    PermissionDefinition('Funcionario', 'deactivate_juntas', 'Desactivar juntas de vecinos', 'funcionario:junta_desactivar', ('funcionario',), (('junta_id', 1),), False),
    PermissionDefinition('Funcionario', 'delete_juntas', 'Eliminar juntas de vecinos sin relaciones', 'funcionario:junta_eliminar', ('funcionario',), (('junta_id', 1),), False),
    
    PermissionDefinition('Funcionario', 'autocomplete_social_applicants', 'Autocompletar solicitantes sociales', 'funcionario:buscar_solicitantes', (), False),
    PermissionDefinition('Funcionario', 'manage_employee_compliance', 'Consultar cumplimiento', 'funcionario:cumplimiento', ('funcionario',)),
    PermissionDefinition('Funcionario', 'manage_social_care', 'Administrar atención social', 'funcionario:atencion_social', ('funcionario',)),
    PermissionDefinition('Funcionario', 'view_social_attention_detail', 'Consultar detalle de atención social', 'funcionario:detalle_atencion_json', ('funcionario',), (('atencion_id', 1),), False),
    PermissionDefinition('Funcionario', 'edit_social_attention_ajax', 'Editar atención social por AJAX', 'funcionario:editar_atencion_ajax', ('funcionario',), (('atencion_id', 1),), False),
    PermissionDefinition('Funcionario', 'access_social_cases', 'Gestionar casos y gestiones sociales', 'funcionario:casos_sociales', ('funcionario',)),
    PermissionDefinition('Funcionario', 'create_social_management_ajax', 'Crear gestión social por AJAX', 'funcionario:crear_gestion_social_ajax', ('funcionario',), (), False),
    PermissionDefinition('Funcionario', 'view_social_management_detail', 'Consultar detalle de gestión social', 'funcionario:detalle_gestion_social_json', ('funcionario',), (('gestion_id', 1),), False),
    PermissionDefinition('Funcionario', 'edit_social_management_ajax', 'Editar gestión social por AJAX', 'funcionario:editar_gestion_social_ajax', ('funcionario',), (('gestion_id', 1),), False),
    PermissionDefinition('Funcionario', 'search_social_applicants', 'Buscar solicitantes', 'funcionario:buscar_solicitantes', ('funcionario',)),
    PermissionDefinition('Funcionario', 'view_social_subattentions', 'Consultar subatenciones por tipo', 'funcionario:subatenciones_tipo', ('funcionario',), (('tipo_id', 1),), False),
    PermissionDefinition('Funcionario', 'manage_collective_agenda', 'Administrar agenda colectiva', 'funcionario:agenda_colectiva', ('funcionario',)),
    PermissionDefinition('Funcionario', 'create_employee_commitments', 'Crear compromisos como Funcionario', 'funcionario:compromiso_nuevo', ('funcionario',)),
    PermissionDefinition('Funcionario', 'edit_employee_commitments', 'Modificar compromisos como Funcionario', 'funcionario:compromiso_editar', ('funcionario',), (('compromiso_id', 1),), False),
    PermissionDefinition('Funcionario', 'upload_commitment_evidence', 'Cargar evidencia de compromisos como Funcionario', 'funcionario:compromiso_evidencia', ('funcionario',), (('compromiso_id', 1),), False),
    
    PermissionDefinition('Supervisor / Verificador', 'review_evidence', 'Revisar y validar evidencias', 'supervisor:home', ('supervisor', 'verificador')),
    PermissionDefinition('Delegado', 'manage_commitments', 'Administrar compromisos', 'delegado:home', ('delegado',)),
    PermissionDefinition('Delegado', 'view_delegation_summary', 'Consultar resumen de delegación', 'delegado:resumen', ('delegado',)),
    PermissionDefinition('Coordinador', 'manage_periods', 'Administrar períodos e indicadores', 'coordinador:home', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Coordinador', 'view_coordinator_personal', 'Consultar desempeño personal de Coordinación', 'coordinador:personal', ('coordinador', 'admin', 'administrador')),
    PermissionDefinition('Consulta', 'view_public_reports', 'Consultar información', 'vistaf:home', ('vistaf', 'consulta', 'usuario de consulta')),
)

PERMISSION_DESCRIPTIONS = {
    'access_admin_dashboard': 'Consultar métricas generales y accesos rápidos de Administración.',
    'access_admin_users': 'Crear, editar y consultar cuentas de usuario.',
    'access_admin_parameters': 'Consultar y modificar parámetros generales del sistema.',
    'access_admin_delegations': 'Crear, editar y administrar delegaciones.',
    'access_admin_positions': 'Crear, editar y administrar cargos.',
    'access_admin_functions': 'Crear, editar y administrar funciones.',
    'access_admin_position_functions': 'Asociar cargos con funciones.',
    'access_admin_roles': 'Crear roles y administrar sus permisos.',
    'access_admin_items': 'Crear, editar y administrar ítems.',
    'access_admin_attention_types': 'Administrar tipos de atención.',
    'access_admin_subattentions': 'Administrar subatenciones.',
    'access_admin_goals': 'Crear y administrar metas.',
    'access_admin_history': 'Consultar el historial de auditoría.',
    'access_admin_password_audit': 'Consultar la auditoría de recuperación de contraseñas.',
    'access_admin_absences': 'Consultar ausencias por delegación.',
    'access_admin_congratulations': 'Consultar felicitaciones por delegación.',
    'access_admin_complaints': 'Consultar reclamos por delegación.',
    'access_admin_milestones': 'Consultar hitos por delegación.',
    'access_admin_neighbors': 'Consultar y administrar vecinos por delegación.',
    'access_admin_neighborhood_associations': 'Consultar y administrar juntas de vecinos por delegación.',
    'access_admin_generated_reports': 'Generar y consultar informes consolidados de todas las delegaciones.',
    'access_admin_delegation_summary': 'Consultar el resumen de cumplimiento de una o todas las delegaciones.',
    'access_admin_records': 'Consultar registros de actividades por delegación.',
    'access_admin_social_attentions': 'Consultar atenciones sociales por delegación.',
    'access_admin_commitments': 'Consultar compromisos por delegación.',
    'access_admin_beneficiados': 'Consultar beneficiados y solicitantes.',
    'create_admin_beneficiados': 'Crear beneficiados desde la administración.',
    'view_admin_beneficiados_detail': 'Consultar el detalle JSON de un beneficiado.',
    'edit_admin_beneficiados': 'Modificar beneficiados desde la administración.',
    'delete_admin_beneficiados': 'Eliminar beneficiados desde la administración.',
    'create_admin_records': 'Crear registros asociados a funcionarios y períodos abiertos.',
    'edit_admin_records': 'Modificar registros dentro de delegaciones autorizadas y períodos abiertos.',
    'create_admin_social_attentions': 'Crear atenciones sociales asociadas a funcionarios.',
    'edit_admin_social_attentions': 'Modificar atenciones sociales dentro de delegaciones autorizadas.',
    'create_admin_commitments': 'Crear compromisos para una delegación y período abierto.',
    'edit_admin_commitments': 'Modificar compromisos dentro de delegaciones autorizadas y períodos abiertos.',
    'manage_admin_goal_adjustments': 'Modificar metas existentes; los períodos cerrados requieren autorización vigente.',
    'create_admin_absences': 'Crear ausencias asociadas a un desempeño.',
    'edit_admin_absences': 'Modificar ausencias dentro del alcance autorizado.',
    'delete_admin_absences': 'Eliminar ausencias cuando no existan referencias protegidas.',
    'create_admin_congratulations': 'Crear felicitaciones asociadas a un desempeño.',
    'edit_admin_congratulations': 'Modificar felicitaciones dentro del alcance autorizado.',
    'delete_admin_congratulations': 'Eliminar felicitaciones protegidas por referencias.',
    'create_admin_complaints': 'Crear reclamos asociados a un desempeño.',
    'edit_admin_complaints': 'Modificar reclamos dentro del alcance autorizado.',
    'delete_admin_complaints': 'Eliminar reclamos protegidos por referencias.',
    'create_admin_milestones': 'Crear hitos territoriales.',
    'edit_admin_milestones': 'Modificar hitos dentro del alcance autorizado.',
    'delete_admin_milestones': 'Eliminar hitos protegidos por referencias.',
    'create_admin_neighbors': 'Crear vecinos desde la administración.',
    'edit_admin_neighbors': 'Modificar vecinos desde la administración.',
    'delete_admin_neighbors': 'Eliminar vecinos desde la administración.',
    'create_admin_juntas': 'Crear juntas de vecinos desde la administración.',
    'edit_admin_juntas': 'Modificar juntas de vecinos desde la administración.',
    'delete_admin_juntas': 'Eliminar juntas de vecinos desde la administración.',
    'access_employee_dashboard': 'Consultar el registro de actividades propio.',
    'manage_employee_activities': 'Crear, editar y eliminar actividades propias.',
    'view_employee_record_detail': 'Consultar el detalle JSON de una actividad para edición.',
    'edit_employee_record_ajax': 'Modificar datos de una actividad mediante AJAX.',
    'access_funcionario_vecinos': 'Consultar vecinos de la delegación.',
    'manage_vecinos': 'Crear, editar, desactivar y eliminar vecinos.',
    'edit_vecinos': 'Modificar datos de vecinos.',
    'view_vecino_detail': 'Consultar detalle JSON de un vecino.',
    'edit_vecino_ajax': 'Modificar vecino por AJAX.',
    'deactivate_vecinos': 'Desactivar vecinos sin eliminar sus datos.',
    'delete_vecinos': 'Eliminar vecinos sin registros asociados.',
    'access_funcionario_juntas': 'Consultar juntas de vecinos de la delegación.',
    'create_juntas': 'Crear juntas de vecinos.',
    'edit_juntas': 'Modificar los datos de juntas de vecinos.',
    'view_junta_detail': 'Consultar detalle JSON de una junta de vecinos.',
    'edit_junta_ajax': 'Modificar junta de vecinos por AJAX.',
    'deactivate_juntas': 'Desactivar juntas de vecinos sin eliminar sus relaciones.',
    'delete_juntas': 'Eliminar juntas de vecinos que no tengan vecinos relacionados.',
    'manage_employee_compliance': 'Consultar el cumplimiento de actividades.',
    'manage_social_care': 'Administrar registros de atención social.',
    'search_social_applicants': 'Buscar solicitantes de atención social.',
    'view_social_subattentions': 'Consultar subatenciones por tipo.',
    'manage_collective_agenda': 'Administrar la agenda colectiva.',
    'create_employee_commitments': 'Crear compromisos propios en la delegación activa.',
    'edit_employee_commitments': 'Modificar datos de compromisos propios sin reasignar responsables.',
    'upload_commitment_evidence': 'Cargar evidencia para compromisos propios.',
    'review_evidence': 'Revisar y validar evidencias de actividades.',
    'manage_commitments': 'Administrar compromisos de la delegación.',
    'view_delegation_summary': 'Consultar el resumen de la delegación.',
    'manage_periods': 'Administrar períodos e indicadores.',
    'view_public_reports': 'Consultar los paneles de información disponibles.',
}

PERMISSION_DESCRIPTIONS['manage_coordinator_periods'] = 'Crear, editar, cerrar y reabrir períodos desde Coordinación.'
PERMISSION_DESCRIPTIONS['manage_coordinator_goals'] = 'Crear, modificar y eliminar metas desde Coordinación.'
PERMISSION_DESCRIPTIONS['manage_coordinator_position_functions'] = 'Asignar funciones a cargos desde Coordinación.'
PERMISSION_DESCRIPTIONS['view_coordinator_weights'] = 'Consultar ponderaciones por cargo o funcionario.'
PERMISSION_DESCRIPTIONS['view_coordinator_reports'] = 'Consultar informes consolidados por período, delegación, cargo y funcionario.'
PERMISSION_DESCRIPTIONS['view_coordinator_trends'] = 'Consultar la evolución histórica del cumplimiento por período, con filtros por delegación, cargo y funcionario.'
PERMISSION_DESCRIPTIONS['request_closed_period_authorization'] = 'Solicitar cambios acotados de metas en períodos cerrados.'
PERMISSION_DESCRIPTIONS['review_closed_period_authorizations'] = 'Aprobar o rechazar solicitudes de cambios en períodos cerrados.'
PERMISSION_DESCRIPTIONS['view_social_attention_detail'] = 'Consultar el detalle JSON de una atención social para edición.'
PERMISSION_DESCRIPTIONS['edit_social_attention_ajax'] = 'Modificar datos de una atención social mediante AJAX.'
PERMISSION_DESCRIPTIONS['access_social_cases'] = 'Consultar y administrar la gestión de casos y gestiones sociales.'
PERMISSION_DESCRIPTIONS['create_social_management_ajax'] = 'Crear una nueva gestión social mediante modal emergente AJAX.'
PERMISSION_DESCRIPTIONS['view_social_management_detail'] = 'Consultar el detalle JSON de una gestión social para edición.'
PERMISSION_DESCRIPTIONS['edit_social_management_ajax'] = 'Modificar fecha u observaciones de una gestión social mediante AJAX.'

PERMISSION_BY_CODENAME = {
    definition.codename: definition
    for definition in PERMISSION_CATALOG
}
PERMISSION_BY_VIEW = {
    definition.view_name: definition
    for definition in PERMISSION_CATALOG
}


def permission_name(codename):
    return f'AdminApp.{codename}'


def _normalize_role_or_cargo_name(name):
    return (name or '').strip().casefold()


def cargo_key_for_access(name):
    normalized = _normalize_role_or_cargo_name(name)
    if normalized in {
        'admin',
        'administrador',
        'administrador del sistema',
    } or normalized.startswith(('administrador ', 'admin ')):
        return 'admin'
    
    if (
        normalized in {'encargado social', 'encargado área social', 'encargado area social'}
        or normalized.startswith(
            ('encargado social', 'encargada social', 'encargado área social', 'encargado area social', 'funcionario ')
        )
    ):
        return 'funcionario'

    if normalized == 'funcionario':
        return 'funcionario'
    if normalized == 'coordinador' or normalized.startswith('coordinador '):
        return 'coordinador'
    if normalized == 'delegado' or normalized.startswith('delegado '):
        return 'delegado'
    if normalized in {'supervisor', 'verificador'}:
        return 'supervisor'
    if normalized in {'vistaf', 'consulta', 'usuario de consulta'}:
        return 'vistaf'
    return None


def _is_matching_cargo(name, cargos):
    cargo_key = cargo_key_for_access(name)
    accepted = {
        cargo_key_for_access(cargo) or _normalize_role_or_cargo_name(cargo)
        for cargo in cargos
    }
    return cargo_key in accepted


def has_cargo_access(user, cargos):
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    cargo = getattr(user, 'cargo', None)
    cargo_name = getattr(cargo, 'nombre', '') if cargo else ''
    if cargo_name:
        if _is_matching_cargo(cargo_name, cargos):
            return True
        if cargo_key_for_access(cargo_name) == 'admin':
            return True

    roles = getattr(user, 'roles', None)
    if roles is None and hasattr(user, 'usuariorol_set'):
        roles = user.usuariorol_set.filter(
            fecha_fin__isnull=True,
        ).select_related('rol')
        role_names = (getattr(user_role.rol, 'nombre', '') for user_role in roles)
    elif hasattr(roles, 'all'):
        role_names = (getattr(role, 'nombre', '') for role in roles.all())
    else:
        role_names = (getattr(role, 'nombre', '') for role in (roles or ()))

    for r_name in role_names:
        if _is_matching_cargo(r_name, cargos):
            return True
        if cargo_key_for_access(r_name) == 'admin':
            return True

    accepted = {
        cargo_key_for_access(cargo) or _normalize_role_or_cargo_name(cargo)
        for cargo in cargos
    }
    if getattr(user, 'is_superuser', False) and 'admin' in accepted:
        return True

    return False


def can_access_permission(user, codename, cargos=()):
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if has_cargo_access(user, cargos):
        return True

    if getattr(user, 'is_superuser', False):
        return True

    if user.has_perm(permission_name(codename)) or user.has_perm(codename):
        return True

    roles = getattr(user, 'roles', None)
    if roles is not None:
        roles_list = roles.all() if hasattr(roles, 'all') else roles
        for role in roles_list:
            raw_perms = getattr(role, 'permisos', '') or ''
            role_perms = {p.strip() for p in raw_perms.split(',') if p.strip()}
            if codename in role_perms:
                return True

    return False