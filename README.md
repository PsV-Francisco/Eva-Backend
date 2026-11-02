# Sistema de Gestión de Resultados (SGR)

## Integrantes

Francisco Andres Alonzo Diaz Moralez

## Descripción

Prototipo académico en Django para registrar actividades, metas, atenciones y evidencias, con acceso por cargo y contexto de delegación. Los datos de demostración son ficticios. Los requisitos formales y el diagrama de clases se conservan en `project_info/`.

## Requisitos e instalación local

- Python 3.12.
- Django 5.2.17 y dependencias fijadas en `requirements.txt`.
- SQLite para desarrollo; MySQL/InnoDB para una instalación compartida.
- `DJANGO_SECRET_KEY` es obligatoria para iniciar la aplicación, también en desarrollo.

En PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:DJANGO_SECRET_KEY = (python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
$env:DB_ENGINE = 'sqlite'
$env:DEBUG = 'True'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/`. La configuración local también puede leerse desde `.env`; no guardes credenciales ni claves reales en Git.

Para dejar la clave solo en el archivo local ignorado por Git, genera una con:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copia el resultado en `DJANGO_SECRET_KEY` dentro de `.env`. No uses una clave de ejemplo, no la compartas ni la subas al repositorio.

## Configuración

La aplicación carga variables del entorno y del archivo `.env` en el directorio raíz. Variables principales:

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | Clave secreta Django; obligatoria para iniciar la aplicación y única por entorno. |
| `DEBUG` | `True` solo en desarrollo; `False` en producción. |
| `ALLOWED_HOSTS` | Hosts HTTP permitidos, separados por coma. |
| `CSRF_TRUSTED_ORIGINS` | Orígenes completos (incluye `https://`), separados por coma; necesario si se usa un dominio distinto al predeterminado. |
| `DB_ENGINE` | `sqlite` o `mysql`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión MySQL; usa una cuenta de base de datos con permisos mínimos. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP para correo de recuperación. |
| `PASSWORD_RESET_DOMAIN` | Host público de los enlaces de recuperación, sin esquema. |
| `PASSWORD_RESET_PROTOCOL` | Protocolo del enlace de recuperación (`http` o `https`); por defecto `http`. En producción con HTTPS, usa `https`. |
| `PASSWORD_RESET_TIMEOUT` | Vigencia del token de enlace en segundos; actualmente 3600 (una hora). |
| `PASSWORD_RESET_RATE_LIMIT`, `PASSWORD_RESET_RATE_WINDOW` | Máximo de solicitudes y ventana en segundos; por defecto 5 y 3600. |
| `PASSWORD_RESET_CODE_TTL_SECONDS` | Vigencia del código; por defecto 600 segundos. |
| `PASSWORD_RESET_CODE_RESEND_SECONDS` | Espera entre reenvíos; por defecto 45 segundos. |
| `PASSWORD_RESET_CODE_MAX_ATTEMPTS` | Intentos de validación permitidos; por defecto 5. |

En desarrollo, los correos se muestran en la consola. En producción, la aplicación usa SMTP. La recuperación principal envía un enlace con `uidb64` y token firmado, válido durante una hora y de uso único. El código de recuperación de seis dígitos sigue disponible como alternativa; se guarda como hash, vence según `PASSWORD_RESET_CODE_TTL_SECONDS` y se invalida después de un uso. Ambos flujos mantienen respuesta genérica, límite de solicitudes y auditoría.

Los accesos se validan en el servidor según el cargo existente. El campo descriptivo `Rol.permisos` no concede permisos efectivos. La delegación activa se limita a las delegaciones autorizadas del usuario.

## Aplicaciones y estado de módulos

Los estados describen el código de esta rama; «operativo» no significa que ya esté desplegado en EC2. Las migraciones aún deben aplicarse en el entorno de destino después de respaldar su base de datos.

| Módulo | Estado | Alcance |
| --- | --- | --- |
| Cabecera, navegación y contexto de delegación | Operativo | Plantilla común, logo institucional, selector restringido a delegaciones autorizadas y navegación por cargo. |
| Acceso y recuperación | Operativo | Inicio de sesión por correo; recuperación por código y auditoría. Requiere SMTP configurado para enviar correo real. |
| Delegaciones, roles y usuarios | Operativo | CRUD, filtros, paginación y exportación XLSX; los permisos continúan basados en cargo. |
| Cargos, funciones, asignaciones y catálogo | Operativo | Mantenedores propios con CRUD, búsqueda y desactivación segura; cargos de control de acceso no se pueden renombrar ni eliminar. |
| Ítems y metas | Operativo | Mantenedor de ítems y asignaciones existentes de metas por usuario, ítem y período. |
| Tipos y Sub Atenciones | Operativo | Catálogos normalizados alimentados con valores históricos; las atenciones históricas conservan sus textos originales. |
| Historial y auditoría de recuperación | Operativo | Vistas de consulta con filtros y paginación; son solo lectura. |
| Registro de actividades y cumplimiento | Operativo | Registro de actividades, evidencias y seguimiento de metas. |
| Ingreso y seguimiento de atenciones | Operativo | Solicitantes locales por delegación, tipo/Sub Atención activa, responsable y fecha automáticos, código de caso y hasta tres seguimientos con evidencia. No consulta padrones externos. |
| Agenda y compromisos | Operativo | Agenda por delegación y actualización de compromisos asignados. |
| Supervisión de evidencias | Operativo | Bandeja de revisión y actualización de estado. |
| Consulta (`VistaFApp`) | Operativo | Vista de consulta disponible dentro de la aplicación; no es una API pública. |
| Datos de demostración | Simulado | Los datos del prototipo son ficticios; no los uses como información municipal real. |
| Despliegue en EC2 | Pendiente | Requiere configurar infraestructura, secretos, SMTP, base de datos, migraciones y pruebas de humo. |

## Evolución del esquema objetivo

El esquema de referencia para la entrega está en `IP-EstructuraDB_29.10.sql`. Su
DDL es una referencia de estructura, no un script para ejecutar: **no ejecutes
su `DROP TABLE` ni lo apliques directamente a una base existente**.

La evolución se hará de forma aditiva y por fases aprobadas:

1. **Documentar decisiones:** mantener `AdminApp.Usuario` basado en
   `AbstractUser` y `AUTH_USER_MODEL`. Los campos requeridos por Django que no
   aparecen en el DDL se conservarán como extensión documentada.
2. **Agregar entidades faltantes del SQL:** crear tablas nuevas para
   `territorio`, `hito`, `felicitacion`, `ausencia`, `reclamo`, `licencia`,
   `informe`, `alertas`, `comentarios`, `periodo_semana`, `cargo_jv` y
   `beneficiado`. Estas tablas usarán los nombres físicos de tabla y columna
   del DDL mediante `db_table` y `db_column`. Las tablas existentes en
   producción conservarán sus nombres y columnas; no se renombrarán en estas
   fases.
3. **Agregar relaciones explícitas de usuario:** crear `UsuarioRol`,
   `UsuarioCargo` y `UsuarioDelegacion` con `through=`, PK simple y fechas de
   vigencia. La delegación principal actual se conservará como una marca en su
   relación. La copia de datos debe ser idempotente y tener operación inversa.
4. **Sincronizar las escrituras:** un único servicio o mecanismo de señales
   será responsable de mantener las asignaciones de roles, cargo y
   delegaciones; formularios, vistas y administración no duplicarán esa
   lógica. Las estructuras actuales permanecerán durante esta etapa.
5. **Validar sin corte:** probar las migraciones en MySQL local restaurado
   desde un `mysqldump`. No se retirarán tablas ni columnas existentes ni se
   cambiará la aplicación a un esquema de corte como parte de este plan.

Todas las tablas nuevas usarán una PK simple compatible con Django. Las PK y
FK compuestas del DDL se representarán con FK simples y restricciones
`UniqueConstraint` donde corresponda. Esta normalización, y las estructuras
actuales que el DDL no contempla —por ejemplo `ParametroSistema`,
`CasoSocial` y `Solicitante`— se conservarán como extensiones documentadas;
no se eliminarán para hacer coincidir literalmente el DDL.

`Beneficiado` se incorpora como entidad paralela a `Solicitante`; no los
fusiona ni reemplaza. Su teléfono se almacena como texto (`VARCHAR(20)` vía
`CharField`) en vez del `INT` del DDL para preservar ceros iniciales y admitir
prefijos internacionales.

En las entidades del Bloque B, `Reclamo.EVIDENCIA` se amplía de
`VARCHAR(100)` a `VARCHAR(1000)`; `Felicitacion.UBICACION` y
`Reclamo.UBICACION` se amplían de `VARCHAR(100)` a `VARCHAR(255)`; y
`Informe.FILTROS` usa `TextField` en lugar de `VARCHAR(200)` para admitir
filtros extensos. Las columnas `DESEMPEÑO` mantienen exactamente la tilde del
DDL en `db_column`. En las relaciones originalmente compuestas, las columnas
dimensionales se mantienen como FKs simples, se completan desde el desempeño o
registro padre al guardar y se validan en `clean()`; esto conserva los datos y
la coherencia de aplicación sin imponer PK compuestas en Django.

En el Bloque C, `Alerta.ENLACE` se amplía de `VARCHAR(200)` a
`VARCHAR(500)`, y `Comentarios.TEXTO` usa `TextField` en lugar de
`VARCHAR(200)`. En `Comentarios`, los grupos de columnas asociados a registro
y compromiso son anulables (a diferencia del DDL); `clean()` exige al menos
uno de los dos padres. Sus dimensiones se completan desde el padre relacionado
al guardar. La columna de responsable de compromiso se rellena solo cuando ese
compromiso tiene exactamente un responsable; con cero o varios responsables
queda nula.

La base de datos real es MySQL. Las pruebas de migración se ejecutarán sobre
una base MySQL local vacía para validar migraciones desde cero, y en una copia
restaurada desde `mysqldump` antes de la Fase 2; nunca directamente sobre
producción.
Después de cada fase se ejecutarán `python manage.py check`,
`python manage.py makemigrations --check --dry-run` y la suite completa con
`DB_ENGINE=sqlite`. Después de cada fase que cree migraciones, también se
validarán esas migraciones en la instancia MySQL local correspondiente a esa
fase. Cada fase requiere
aprobación antes de implementarse; no se crearán commits como parte del plan.

## Rutas principales

- `FuncionarioApp`: `/funcionario/`, `/funcionario/cumplimiento/`, `/funcionario/atencion-social/` y `/funcionario/agenda-colectiva/`.
- `SupervisorApp`: `/supervisor/` para revisar evidencias.
- `DelegadoApp`: `/delegado/` y `/delegado/resumen/`.
- `CoordinadorApp`: `/coordinador/`.
- `AdminApp`: `/admin-app/`, `/admin-app/parametros/` y mantenedores de `/admin-app/cargos/`, `/admin-app/funciones/`, `/admin-app/cargos-funciones/`, `/admin-app/catalogo/`, `/admin-app/delegaciones/`, `/admin-app/roles/`, `/admin-app/items/`, `/admin-app/tipos-atencion/` y `/admin-app/subatenciones/`. Las consultas de historial y recuperación están en `/admin-app/historial/` y `/admin-app/auditoria-recuperacion/`.
- `VistaFApp`: `/consulta/`.

Los cargos `Supervisor` y `Verificador` son distintos; ambos pueden ingresar al portal de supervisión sin que el sistema convierta o asigne automáticamente un cargo al otro. `Templates/base.html` es la plantilla compartida; los recursos estáticos se publican desde `static/`.

## Pruebas y comprobaciones

```powershell
$env:DB_ENGINE = 'sqlite'
$env:DEBUG = 'True'
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

La suite de esta rama cubre los flujos de acceso, mantenedores, permisos y atención. No ejecutes migraciones contra una base de producción como parte de estas comprobaciones.

### Vista previa del correo de recuperación

Con `DEBUG=True`, Django imprime los correos en la consola en lugar de enviarlos. Para previsualizar el HTML en el navegador, guarda una vista previa temporal. En este archivo local se reemplaza el CID por una ruta de archivo para que el navegador también pueda mostrar el logo:

```powershell
python manage.py shell -c "import tempfile; from pathlib import Path; from django.template.loader import render_to_string; html = render_to_string('emails/recuperar_codigo.html', {'nombre': 'Nombre de prueba', 'codigo': '123456', 'minutos': 10}); html = html.replace('cid:logo_serena', (Path('static/img/logo.png').resolve()).as_uri()); output = Path(tempfile.gettempdir()) / 'recuperar_codigo_preview.html'; output.write_text(html, encoding='utf-8'); print(output)"
```

Abre la ruta impresa en un navegador. El correo real conserva la imagen CID. Este comando solo renderiza la plantilla y guarda un HTML temporal: no envía ningún correo.

## Despliegue en EC2

1. Prepara una instancia Linux con Python 3.12, Nginx, herramientas de compilación y dependencias de MySQL (`default-libmysqlclient-dev` en Ubuntu). Limita SSH en el grupo de seguridad a las IP administrativas y habilita HTTP/HTTPS según la configuración del proxy.
2. Despliega la rama/revisión aprobada en un directorio de la instancia, crea el entorno virtual e instala dependencias:

   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Antes de desplegar o iniciar el servicio**, crea un archivo de entorno protegido (por ejemplo, `/etc/sgr/sgr.env`, permisos `600`) y agrega `DJANGO_SECRET_KEY` con una clave nueva. Puedes generarla en el servidor con `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` y guardarla en ese archivo; no la escribas en el repositorio ni en logs. La aplicación ahora falla al arrancar si falta la variable. Define también `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_ENGINE=mysql`, las variables `DB_*`, SMTP, `PASSWORD_RESET_DOMAIN=sgr.ejemplo.cl` y `PASSWORD_RESET_PROTOCOL=https`. Configura el protocolo como `https` solo cuando el dominio ya esté publicado detrás de HTTPS.
4. Configura MySQL o RDS con InnoDB, crea una base y una cuenta de servicio de privilegios mínimos. Permite conexiones solo desde el grupo de seguridad de EC2 y respalda la base de destino antes de actualizarla.
5. Desde el directorio de la aplicación, activa el entorno virtual y verifica la configuración antes de tocar la base:

   ```bash
   python manage.py check --deploy
   python manage.py migrate --plan
   ```

   Revisa el plan y el respaldo. Luego aplica las migraciones aprobadas con `python manage.py migrate` y publica los estáticos con `python manage.py collectstatic --noinput`. Las migraciones de esta rama agregan campos y catálogos; no las ejecutes sobre datos reales sin respaldo y revisión del plan.
6. Ejecuta `config.wsgi:application` con Gunicorn bajo un servicio `systemd`, enlazado solo a `127.0.0.1` o a un socket Unix. Como guía, el servicio puede iniciar con:

   ```ini
   [Service]
   User=sgr
   Group=www-data
   WorkingDirectory=/opt/sgr
   EnvironmentFile=/etc/sgr/sgr.env
   ExecStart=/opt/sgr/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 config.wsgi:application
   Restart=on-failure
   ```

   Configura Nginx como proxy inverso hacia `127.0.0.1:8000` y sirve `/static/` desde `/opt/sgr/staticfiles/`. Mantén el proceso bajo un usuario del sistema sin privilegios y habilita HTTPS con un certificado válido antes de usar el sitio públicamente.
7. Reinicia el servicio, verifica `systemctl status <servicio>` y los logs, y prueba en el sitio: login, recepción del enlace de recuperación por SMTP y su vencimiento/uso único, recuperación por código alternativa, cambio de delegación autorizada, CRUD/exportación, alta de atención, relación tipo/Sub Atención y acceso denegado a rutas no autorizadas.
8. Mantén respaldos y monitoreo de base y medios. No uses `runserver` como servidor de producción.

## Roles y permisos

Los roles se administran desde **Administración → Roles**. Cada rol mantiene un
grupo de Django asociado y sus permisos son permisos Django (`Group` y
`Permission`); las asignaciones del usuario se sincronizan con sus grupos. La
migración `AdminApp.0013_alter_rol_options_rol_grupo_rol_protegido` crea el
catálogo y los grupos existentes de forma idempotente. No hay un comando
manual de inicialización.

La autorización conserva los accesos del cargo actual y concede acceso
adicional si uno de los roles activos del usuario contiene el permiso de la
vista. Un rol no revoca accesos heredados del cargo. El cargo `admin` o
`administrador` mantiene acceso total. Una cuenta superusuario sin ese cargo no
obtiene un bypass automático de las restricciones de la aplicación. Los
permisos adicionales respetan además los filtros de delegación y las reglas de
negocio existentes.

Las cuentas no administradoras que gestionen usuarios o roles solo pueden
asignar permisos que su propia cuenta ya posee. La aplicación registra en el
Historial la creación, edición, duplicación y eliminación de roles y los
cambios de asignación de roles a usuarios. Los roles marcados como protegidos
(incluidos los nombres críticos preexistentes) no se pueden editar ni eliminar.
La última cuenta Administrador activa no se puede desactivar, degradar ni
eliminar; estas restricciones se aplican también en el servidor.

### Permiso y vistas protegidas

El catálogo está definido en `config/permissions.py`. El chequeo de Django
verifica que cada vista protegida por `cargo_required` tenga una asociación
exacta con el catálogo.

| Módulo | Permiso | Vista protegida |
|---|---|---|
| Administración | `access_admin_users` | `administracion:home` |
| Administración | `access_admin_parameters` | `administracion:parametros` |
| Administración | `access_admin_delegations` | `administracion:delegaciones` |
| Administración | `access_admin_positions` | `administracion:cargos` |
| Administración | `access_admin_functions` | `administracion:funciones` |
| Administración | `access_admin_position_functions` | `administracion:cargos-funciones` |
| Administración | `access_admin_catalog` | `administracion:catalogo` |
| Administración | `access_admin_roles` | `administracion:roles` |
| Administración | `access_admin_items` | `administracion:items` |
| Administración | `access_admin_attention_types` | `administracion:tipos-atencion` |
| Administración | `access_admin_subattentions` | `administracion:subatenciones` |
| Administración | `access_admin_goals` | `administracion:metas` |
| Administración | `access_admin_history` | `administracion:historial` |
| Administración | `access_admin_password_audit` | `administracion:auditoria-recuperacion` |
| Funcionario | `access_employee_dashboard` | `funcionario:home` |
| Funcionario | `manage_employee_compliance` | `funcionario:cumplimiento` |
| Funcionario | `manage_social_care` | `funcionario:atencion_social` |
| Funcionario | `search_social_applicants` | `funcionario:buscar_solicitantes` |
| Funcionario | `view_social_subattentions` | `funcionario:subatenciones_tipo` |
| Funcionario | `manage_collective_agenda` | `funcionario:agenda_colectiva` |
| Supervisor / Verificador | `review_evidence` | `supervisor:home` |
| Delegado | `manage_commitments` | `delegado:home` |
| Delegado | `view_delegation_summary` | `delegado:resumen` |
| Coordinador | `manage_periods` | `coordinador:home` |
| Consulta | `view_public_reports` | `vistaf:home` |
