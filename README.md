# SGR - Mock-up interactivo

Prototipo frontend del Sistema de Gestión de Resultados (SGR), construido a partir del documento formal de requerimientos del proyecto integrado.

## Ejecutar con Django

El prototipo ahora se sirve mediante una aplicación Django. En PowerShell, desde la carpeta raíz:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Luego abrir `http://127.0.0.1:8000/`.

Si PowerShell bloquea la activación del entorno, se puede ejecutar directamente:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Rutas disponibles:

- `GET /` - interfaz del prototipo SGR.
- `GET /funcionario/` - registro y seguimiento personal.
- `GET /supervisor/` - revisión de evidencias y monitoreo.
- `GET /delegado/` - seguimiento de delegación y compromisos.
- `GET /coordinador/` - medición, períodos e informes.
- `GET /admin-app/` - configuración y auditoría.
- `GET /api/health/` - comprobación del backend.
- `GET /api/roles/` - roles disponibles para la demostración.
- `/static/css/`, `/static/js/`, `/static/data/` - recursos servidos por Django.

Para detener el servidor, pulsar `Ctrl + C`.

## Arquitectura Django

```text
config/       Configuración, ASGI, WSGI, API general y enrutamiento principal.
FuncionarioApp/ Registro de actividades, compromisos y desempeño personal.
SupervisorApp/ Revisión de evidencias y monitoreo de gestión.
DelegadoApp/  Seguimiento de resultados y compromisos de delegación.
CoordinadorApp/ Metas, períodos e informes de gestión.
AdminApp/     Usuarios, catálogos, parámetros y auditoría.
VistaFApp/    Aplicación registrada, pendiente de definición de templates.
Templates/    Plantillas por aplicación y base.html compartida.
static/       CSS, JavaScript, JSON e imágenes.
manage.py     Punto de entrada de comandos Django.
.venv/        Entorno virtual local, excluido de Git.
```

Las vistas de rol comparten la interfaz del prototipo y abren con el perfil de demostración correspondiente. `VistaFApp` queda sin rutas ni templates hasta confirmar su diseño. La autorización y persistencia siguen siendo simuladas en el frontend; deben implementarse en el backend antes de producción.

## Alcance implementado

- Panel personal y resumen de delegación.
- Datos ficticios cargados desde JSON.
- Registro de actividades con generación de código único.
- Evidencias con carga simulada y validación por rol.
- Agenda colectiva con estados e historial.
- Cálculo de avance, cumplimiento, ponderación y semáforo.
- Filtros y exportación CSV.
- Vista de auditoría simulada.
- Bootstrap 5.3.3 y Bootstrap Icons.
- SweetAlert2 11 para confirmaciones y mensajes.

## Roles de demostración

El selector de perfil se abre desde el nombre de usuario en la barra lateral. Los roles disponibles son Coordinadora, Delegado, Funcionario y Verificadora. El cambio de rol es una simulación visual para recorrer los flujos del mock-up.

## Reglas base

- Cumplimiento: `avance aprobado / meta x 100`.
- Resultado ponderado: `ponderador x cumplimiento / 100`.
- Tope inicial configurable: `150 %`.
- Semáforo verde: avance igual o superior a la meta esperada.
- Semáforo ámbar: avance desde el `60 %` de la meta esperada y menor que ella.
- Semáforo rojo: avance inferior al `60 %` de la meta esperada.

## Limitaciones del mock-up

Los cambios se mantienen en memoria durante la sesión y no reemplazan una API, base de datos, autenticación real, control de acceso del servidor ni almacenamiento seguro de evidencias. La carga de archivos solo registra metadatos ficticios. No se incluyen presupuesto, remuneraciones, firma electrónica ni integraciones municipales.
