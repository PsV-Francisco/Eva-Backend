# Sistema de Gestión de Resultados

Backend Django organizado por aplicaciones de rol. Los requisitos formales y el diagrama de clases se conservan en `project_info/`.

## Requisitos

- Python y el entorno virtual local `.venv`.
- Django instalado desde `requirements.txt`.
- SQLite para desarrollo local. La configuración permite seleccionar MySQL mediante variables de entorno cuando el servidor y el controlador estén preparados.

## Ejecución local

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/`.

## Aplicaciones y rutas

- `FuncionarioApp`: `/funcionario/` (registro), `/funcionario/cumplimiento/`, `/funcionario/atencion-social/` y `/funcionario/agenda-colectiva/`.
- `SupervisorApp`: `/supervisor/` (bandeja y revisión de evidencias).
- `DelegadoApp`: `/delegado/` (agenda y compromisos) y `/delegado/resumen/`.
- `CoordinadorApp`: `/coordinador/`
- `AdminApp`: `/admin-app/` y `/admin-app/parametros/`.
- `VistaFApp`: `/consulta/` (vista de consulta).

Los cargos `Supervisor` y `Verificador` son distintos. Ambos pueden ingresar al portal `/supervisor/` para revisar evidencias; el sistema no convierte ni asigna automáticamente un cargo o rol al otro.

`Templates/base.html` es la plantilla compartida por las páginas SGR. `static/` queda disponible para recursos propios del backend.

Las pruebas de los flujos principales se ejecutan con:

```powershell
python manage.py test AdminApp.tests AdminApp.test_password_reset CoordinadorApp.tests FuncionarioApp.tests DelegadoApp.tests SupervisorApp.tests
```

Atención social conserva los registros anteriores: la migración crea un caso para cada `AtencionSocial` existente y asigna códigos a las gestiones antiguas.

## Recuperación de contraseña

El acceso incluye recuperación de contraseña con enlaces de un solo uso que vencen en una hora. El sitio registra las solicitudes y los cambios de contraseña en la auditoría de administración; el correo solicitado se almacena como una huella HMAC, no como texto plano. Se permiten hasta cinco solicitudes por hora para cada IP y correo.

En desarrollo (`DEBUG=True`) los mensajes se imprimen en la consola. En producción (`DEBUG=False`), configura estas variables en el entorno del servicio:

| Variable | Uso | Valor sugerido |
| --- | --- | --- |
| `EMAIL_HOST` | Servidor SMTP | Host SMTP de tu proveedor |
| `EMAIL_PORT` | Puerto SMTP | `587` |
| `EMAIL_USE_TLS` | Usar STARTTLS | `True` |
| `EMAIL_HOST_USER` | Usuario SMTP | Usuario del proveedor |
| `EMAIL_HOST_PASSWORD` | Clave SMTP | Secreto del proveedor; no guardarlo en el repositorio |
| `DEFAULT_FROM_EMAIL` | Remitente verificado | Dirección autorizada por el proveedor |
| `ALLOWED_HOSTS` | Hosts HTTP aceptados, separados por coma | `3.228.118.5` y el dominio público si existe |
| `PASSWORD_RESET_DOMAIN` | Host canónico incluido en los enlaces de recuperación, sin esquema | `3.228.118.5` o el dominio público |

En producción, la configuración inicial acepta solo `3.228.118.5`; en desarrollo, acepta `localhost` y `127.0.0.1`. Define `PASSWORD_RESET_DOMAIN` para fijar el host público del enlace (por defecto `3.228.118.5`), independientemente del encabezado `Host` de la solicitud. Si Nginx funciona como proxy, configura de forma segura el reenvío de la IP real del cliente para que `REMOTE_ADDR` permita aplicar el límite por IP.

### Despliegue en EC2

1. Configura las variables SMTP anteriores en el archivo de entorno protegido que carga el servicio (por ejemplo, `EnvironmentFile` de systemd). Define `DEBUG=False`, `ALLOWED_HOSTS=3.228.118.5` (añade el dominio si lo usas), y no pongas credenciales en el repositorio.
2. Desde el directorio de la aplicación y con el entorno virtual activo, ejecuta `python manage.py migrate` para crear las tablas de auditoría y sincronización del límite. No hay migraciones de datos existentes que convertir.
3. Reinicia el servicio Django, por ejemplo `sudo systemctl restart <nombre-del-servicio>`, y comprueba su estado con `sudo systemctl status <nombre-del-servicio>`.
4. Abre `http://3.228.118.5/`, selecciona «¿Olvidaste tu contraseña?» e ingresa el correo de una cuenta activa. Verifica que llegue el mensaje SMTP y que su enlace use el host correcto.
5. Abre el enlace, guarda una contraseña que cumpla los validadores y prueba iniciar sesión con ella. Confirma también que una dirección no registrada muestra la misma pantalla de confirmación y que el enlace no funciona tras usarse o al vencer.

## Seleccionar MySQL

Configurar `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT` en el entorno. No guardar credenciales en el repositorio. El controlador MySQL y la instancia AWS se configuran por separado antes de migrar.
