# Sistema de Gestión de Resultados (SGR)

## Integrantes

Pendiente de completar por el equipo: el repositorio no identifica los nombres de sus integrantes.

## Descripción

Prototipo académico en Django para registrar actividades, metas, atenciones y evidencias, con acceso por cargo y contexto de delegación. Los datos de demostración son ficticios. Los requisitos formales y el diagrama de clases se conservan en `project_info/`.

## Requisitos e instalación local

- Python 3.12.
- Django 5.2.17 y dependencias fijadas en `requirements.txt`.
- SQLite para desarrollo; MySQL/InnoDB para una instalación compartida.

En PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:DB_ENGINE = 'sqlite'
$env:DEBUG = 'True'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/`. La configuración local también puede leerse desde `.env`; no guardes credenciales ni claves reales en Git.

## Configuración

La aplicación carga variables del entorno y del archivo `.env` en el directorio raíz. Variables principales:

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | Clave secreta Django; obligatoria y única en producción. |
| `DEBUG` | `True` solo en desarrollo; `False` en producción. |
| `ALLOWED_HOSTS` | Hosts HTTP permitidos, separados por coma. |
| `CSRF_TRUSTED_ORIGINS` | Orígenes completos (incluye `https://`), separados por coma; necesario si se usa un dominio distinto al predeterminado. |
| `DB_ENGINE` | `sqlite` o `mysql`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión MySQL; usa una cuenta de base de datos con permisos mínimos. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP para correo de recuperación. |
| `PASSWORD_RESET_DOMAIN` | Host público de los enlaces de recuperación, sin esquema. |
| `PASSWORD_RESET_RATE_LIMIT`, `PASSWORD_RESET_RATE_WINDOW` | Máximo de solicitudes y ventana en segundos; por defecto 5 y 3600. |
| `PASSWORD_RESET_CODE_TTL_SECONDS` | Vigencia del código; por defecto 600 segundos. |
| `PASSWORD_RESET_CODE_RESEND_SECONDS` | Espera entre reenvíos; por defecto 45 segundos. |
| `PASSWORD_RESET_CODE_MAX_ATTEMPTS` | Intentos de validación permitidos; por defecto 5. |

En desarrollo, los correos se muestran en la consola. En producción, la aplicación usa SMTP. El código de recuperación es de seis dígitos, se guarda como hash, vence según `PASSWORD_RESET_CODE_TTL_SECONDS` y se invalida después de un uso.

Los accesos se validan en el servidor según el cargo existente. El campo descriptivo `Rol.permisos` no concede permisos efectivos. La delegación activa se limita a las delegaciones autorizadas del usuario.

## Aplicaciones y estado de módulos

Los estados describen el código de esta rama; «operativo» no significa que ya esté desplegado en EC2. Las migraciones aún deben aplicarse en el entorno de destino después de respaldar su base de datos.

| Módulo | Estado | Alcance |
| --- | --- | --- |
| Cabecera, navegación y contexto de delegación | Operativo | Plantilla común, logo institucional, selector restringido a delegaciones autorizadas y navegación por cargo. |
| Acceso y recuperación | Operativo | Inicio de sesión por correo; recuperación por código y auditoría. Requiere SMTP configurado para enviar correo real. |
| Delegaciones, roles y usuarios | Operativo | CRUD, filtros, paginación y exportación XLSX; los permisos continúan basados en cargo. |
| Ítems y metas | Operativo | Mantenedor de ítems y asignaciones existentes de metas por usuario, ítem y período. |
| Tipos y Sub Atenciones | Operativo | Catálogos normalizados alimentados con valores históricos; las atenciones históricas conservan sus textos originales. |
| Registro de actividades y cumplimiento | Operativo | Registro de actividades, evidencias y seguimiento de metas. |
| Ingreso y seguimiento de atenciones | Operativo | Solicitantes locales por delegación, tipo/Sub Atención activa, responsable y fecha automáticos, código de caso y hasta tres seguimientos con evidencia. No consulta padrones externos. |
| Agenda y compromisos | Operativo | Agenda por delegación y actualización de compromisos asignados. |
| Supervisión de evidencias | Operativo | Bandeja de revisión y actualización de estado. |
| Consulta (`VistaFApp`) | Operativo | Vista de consulta disponible dentro de la aplicación; no es una API pública. |
| Datos de demostración | Simulado | Los datos del prototipo son ficticios; no los uses como información municipal real. |
| Despliegue en EC2 | Pendiente | Requiere configurar infraestructura, secretos, SMTP, base de datos, migraciones y pruebas de humo. |

## Rutas principales

- `FuncionarioApp`: `/funcionario/`, `/funcionario/cumplimiento/`, `/funcionario/atencion-social/` y `/funcionario/agenda-colectiva/`.
- `SupervisorApp`: `/supervisor/` para revisar evidencias.
- `DelegadoApp`: `/delegado/` y `/delegado/resumen/`.
- `CoordinadorApp`: `/coordinador/`.
- `AdminApp`: `/admin-app/`, `/admin-app/parametros/` y los mantenedores de `/admin-app/delegaciones/`, `/admin-app/roles/`, `/admin-app/items/`, `/admin-app/tipos-atencion/` y `/admin-app/subatenciones/`.
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

## Despliegue en EC2

1. Prepara una instancia Linux con Python 3.12, Nginx, herramientas de compilación y dependencias de MySQL (`default-libmysqlclient-dev` en Ubuntu). Limita SSH en el grupo de seguridad a las IP administrativas y habilita HTTP/HTTPS según la configuración del proxy.
2. Despliega la rama/revisión aprobada en un directorio de la instancia, crea el entorno virtual e instala dependencias:

   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Crea un archivo de entorno protegido para el servicio (por ejemplo, `/etc/sgr/sgr.env`, permisos `600`). Define `DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_ENGINE=mysql`, las variables `DB_*`, SMTP y `PASSWORD_RESET_DOMAIN`. No copies secretos al repositorio ni a los logs. Para un dominio, por ejemplo, usa `ALLOWED_HOSTS=sgr.ejemplo.cl` y `CSRF_TRUSTED_ORIGINS=https://sgr.ejemplo.cl`.
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
7. Reinicia el servicio, verifica `systemctl status <servicio>` y los logs, y prueba en el sitio: login, recuperación SMTP, cambio de delegación autorizada, CRUD/exportación, alta de atención, relación tipo/Sub Atención y acceso denegado a rutas no autorizadas.
8. Mantén respaldos y monitoreo de base y medios. No uses `runserver` como servidor de producción.
