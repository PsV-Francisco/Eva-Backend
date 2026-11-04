from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required

from config.permissions import cargo_key_for_access


MANUALS = {
    'administrador': {
        'label': 'Administrador',
        'summary': 'Gestiona usuarios, delegaciones, funciones, roles, precedentes del sistema y supervisa el funcionamiento general.',
        'screens': [
            'Usuarios: crea, edita, activa o desactiva cuentas y asigna delegaciones y roles.',
            'Cargos y funciones: administra los cargos base y las funciones asociadas.',
            'Delegaciones: define y mantiene los ámbitos territoriales del sistema.',
            'Items y metas: administra indicadores y planes de desempeño.',
            'Roles y permisos: revisa y mantiene los perfiles de acceso.',
            'Historial y auditoría: revisa cambios del sistema y auditoría de recuperación.',
        ],
        'steps': [
            '1. Inicia sesión con tu correo y contraseña.',
            '2. Revisa la pantalla de Usuarios para mantener cuentas y delegaciones.',
            '3. Configura roles, funciones, cargos y parametrización desde Administración.',
            '4. Revisa la auditoría y el historial de cada operación sensible.',
            '5. Valida que los períodos, delegaciones y permisos estén coherentes antes de cerrar ciclos.',
        ],
        'rules': [
            'Los cargos críticos del sistema no pueden renombrarse ni eliminarse.',
            'Las cuentas propias o superadministradoras no pueden desactivarse ni borrarse.',
            'Los usuarios deben tener una delegación activa según el contexto autorizado.',
            'Las acciones sensibles quedan registradas en historial y auditoría.',
        ],
        'faq': [
            '¿Puedo ver todos los manuales? Sí, desde esta vista el Administrador puede abrir cualquier manual del sistema.',
            '¿Qué pasa si no sé qué perfil tiene un usuario? Revisa la pantalla de Usuarios y su cargo/roles asignados.',
            '¿Dónde veo la auditoría? En la sección de historial y auditoría de recuperación.',
        ],
        'screenshot': 'Espacio para captura: panel de Administración general.',
    },
    'coordinador': {
        'label': 'Coordinador',
        'summary': 'Administra los períodos, metas e indicadores del sistema y controla cierres y reaperturas.',
        'screens': [
            'Metas e indicadores: revisa y configura períodos, metas y estados.',
            'Avance esperado: visualiza el estado general de cumplimiento.',
            'Gestión de periodos: crea, edita, cierra y reabre períodos abiertos.',
        ],
        'steps': [
            '1. Inicia sesión con tu cuenta y usa la delegación autorizada.',
            '2. Abre la pantalla de coordinación para ver los períodos vigentes.',
            '3. Crea o modifica un período cuando corresponda.',
            '4. Cierra un período cuando el ciclo termina y no permita más cambios.',
            '5. Reabre un período solo si se requiere ajustar información cerrada.',
        ],
        'rules': [
            'Los períodos cerrados pasan a ser de solo lectura.',
            'No se pueden eliminar períodos con información asociada.',
            'Las evidencias y registros vinculados a un período cerrado no deben modificarse.',
        ],
        'faq': [
            '¿Qué pasa si quiero eliminar un período? Solo se permite si no tiene información asociada y está abierto.',
            '¿Puedo reabrir un período? Sí, siempre que el perfil y el estado lo permitan.',
        ],
        'screenshot': 'Espacio para captura: gestión de periodos y metas.',
    },
    'delegado': {
        'label': 'Delegado',
        'summary': 'Gestiona la agenda de compromisos de la delegación y actualiza los estados de cada gestión.',
        'screens': [
            'Agenda colectiva: crea o edita compromisos de la delegación.',
            'Resumen de la delegación: revisa el conjunto de compromisos y sus estados.',
            'Cambios de estado: actualiza la condición del compromiso según su avance.',
        ],
        'steps': [
            '1. Inicia sesión con tu cuenta y selecciona la delegación activa.',
            '2. Revisa la agenda de compromiso del período vigente.',
            '3. Crea o edita compromisos asociados a la delegación.',
            '4. Cambia el estado del compromiso cuando corresponde.',
            '5. Verifica que el período siga abierto antes de modificar un compromiso.',
        ],
        'rules': [
            'No se pueden modificar compromisos con evidencias asociadas.',
            'Los compromisos de un período cerrado son de solo lectura.',
            'Cada cambio de estado queda registrado en el historial del compromiso.',
        ],
        'faq': [
            '¿Qué hago si el compromiso ya tiene evidencia? No es editable; primero revisa si corresponde otra acción.',
            '¿Puedo cambiar la delegación activa? Sí, solo entre las autorizadas para tu cuenta.',
        ],
        'screenshot': 'Espacio para captura: agenda de compromisos y cambio de estado.',
    },
    'funcionario': {
        'label': 'Funcionario',
        'summary': 'Registra actividades, atiende casos sociales y revisa su cumplimiento en los periodos asignados.',
        'screens': [
            'Registro de actividades: crea y edita actividades del periodo abierto.',
            'Atención social: registra casos, solicitantes y gestiones.',
            'Agenda colectiva: revisa la agenda asociada a la delegación.',
            'Cumplimiento: consulta el desempeño por período e ítems asignados.',
        ],
        'steps': [
            '1. Inicia sesión con tu cuenta y verifica tu delegación activa.',
            '2. Registra una actividad en la pantalla principal, con código, item y periodo.',
            '3. Si corresponde, agrega evidencia a la actividad registrada.',
            '4. Consulta la pestaña de atención social para levantar casos asociados.',
            '5. Revisa tu cumplimiento en la sección del período asignado.',
        ],
        'rules': [
            'Las actividades solo se editan si están pendientes y el período está abierto.',
            'No se pueden eliminar actividades que ya tienen evidencias asociadas.',
            'La validación de evidencias puede dejar una actividad observada o validada.',
        ],
        'faq': [
            '¿Puedo modificar una actividad si ya fue revisada? Depende del estado; revisa si la actividad queda en período abierto y pendiente.',
            '¿Dónde se ven mis resultados? En la sección de Cumplimiento.',
        ],
        'screenshot': 'Espacio para captura: registro de actividades y cumplimiento.',
    },
    'supervisor': {
        'label': 'Verificador / Supervisor',
        'summary': 'Revisa evidencias y valida que la información registrada cumpla con el estándar del sistema.',
        'screens': [
            'Validar evidencias: revisa las evidencias pendientes y toma decisiones.',
            'Historial de revisiones: consulta las validaciones realizadas por el usuario.',
        ],
        'steps': [
            '1. Inicia sesión con tu cuenta y revisa la delegación activa o el alcance disponible.',
            '2. Abre la pantalla de validación de evidencias.',
            '3. Selecciona una evidencia pendiente y decide si aprueba o rechaza.',
            '4. Guarda la observación asociada en el caso que corresponda.',
            '5. Revisa luego el historál de validaciones para confirmar el cierre del proceso.',
        ],
        'rules': [
            'Las evidencias de un período cerrado son de solo lectura.',
            'Una evidencia ya revisada no puede volver a cambiarse en la misma pantalla.',
            'La decisión de aprobación o rechazo afecta el estado del registro o compromiso asociado.',
        ],
        'faq': [
            '¿Qué pasa si la evidencia está en un período cerrado? No se podrá modificar ni validar en ese estado.',
            '¿Dónde veo las decisiones anteriores? En la sección de revisiones del propio verificador.',
        ],
        'screenshot': 'Espacio para captura: validación de evidencias.',
    },
    'verificador': {
        'label': 'Verificador / Supervisor',
        'summary': 'Revisa evidencias y valida que la información registrada cumpla con el estándar del sistema.',
        'screens': [
            'Validar evidencias: revisa las evidencias pendientes y toma decisiones.',
            'Historial de revisiones: consulta las validaciones realizadas por el usuario.',
        ],
        'steps': [
            '1. Inicia sesión con tu cuenta y revisa la delegación activa o el alcance disponible.',
            '2. Abre la pantalla de validación de evidencias.',
            '3. Selecciona una evidencia pendiente y decide si aprueba o rechaza.',
            '4. Guarda la observación asociada en el caso que corresponda.',
            '5. Revisa luego el historál de validaciones para confirmar el cierre del proceso.',
        ],
        'rules': [
            'Las evidencias de un período cerrado son de solo lectura.',
            'Una evidencia ya revisada no puede volver a cambiarse en la misma pantalla.',
            'La decisión de aprobación o rechazo afecta el estado del registro o compromiso asociado.',
        ],
        'faq': [
            '¿Qué pasa si la evidencia está en un período cerrado? No se podrá modificar ni validar en ese estado.',
            '¿Dónde veo las decisiones anteriores? En la sección de revisiones del propio verificador.',
        ],
        'screenshot': 'Espacio para captura: validación de evidencias.',
    },
}


def _role_key(name):
    return (name or '').strip().casefold()


@login_required
def home_redirect(request):
    cargo = getattr(request.user, 'cargo', None)
    cargo_name = _role_key(getattr(cargo, 'nombre', ''))

    cargo_routes = {
        'funcionario': 'funcionario:home',
        'supervisor': 'supervisor:home',
        'verificador': 'supervisor:home',
        'delegado': 'delegado:home',
        'coordinador': 'coordinador:home',
        'admin': 'administracion:home',
        'administrador': 'administracion:home',
        'vistaf': 'vistaf:home',
        'consulta': 'vistaf:home',
        'usuario de consulta': 'vistaf:home',
    }
    cargo_key = cargo_key_for_access(cargo_name)
    route_name = cargo_routes.get(cargo_key)

    if route_name is None:
        roles = getattr(request.user, 'roles', None)
        if roles is None and hasattr(request.user, 'usuariorol_set'):
            roles = request.user.usuariorol_set.filter(
                fecha_fin__isnull=True,
            ).select_related('rol')
            role_names = (
                getattr(user_role.rol, 'nombre', '')
                for user_role in roles
            )
        elif hasattr(roles, 'all'):
            role_names = (
                getattr(role, 'nombre', '')
                for role in roles.all()
            )
        else:
            role_names = (
                getattr(role, 'nombre', '')
                for role in (roles or ())
            )

        for role_name in role_names:
            route_name = cargo_routes.get(cargo_key_for_access(role_name))
            if route_name:
                break

    if route_name is None:
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            route_name = 'administracion:home'
        else:
            raise PermissionDenied

    return redirect(route_name)


@login_required
def manual(request, role=None):
    user_cargo = request.user.cargo
    user_cargo_key = _role_key(getattr(user_cargo, 'nombre', '')) if user_cargo else ''
    is_admin = user_cargo_key in {'admin', 'administrador'}

    if role is None:
        if is_admin:
            return render(request, 'config/manual_index.html', {
                'manuals': [
                    {'key': key, 'label': data['label'], 'summary': data['summary']}
                    for key, data in MANUALS.items()
                ],
                'user_cargo': user_cargo_key,
                'sgr_role': 'Administración',
            })
        if user_cargo_key not in MANUALS:
            raise PermissionDenied
        role = user_cargo_key

    role_key = _role_key(role)
    if role_key not in MANUALS:
        raise PermissionDenied
    if not is_admin and role_key != user_cargo_key:
        raise PermissionDenied

    manual_data = MANUALS[role_key]
    return render(request, 'config/manual.html', {
        'manual': manual_data,
        'role_key': role_key,
        'user_cargo': user_cargo_key,
        'is_admin': is_admin,
        'sgr_role': manual_data['label'],
    })