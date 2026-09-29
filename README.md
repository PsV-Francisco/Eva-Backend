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

- `FuncionarioApp`: `/funcionario/`
- `SupervisorApp`: `/supervisor/`
- `DelegadoApp`: `/delegado/`
- `CoordinadorApp`: `/coordinador/`
- `AdminApp`: `/admin-app/`
- `VistaFApp`: registrada, pendiente de definición de vista y templates.
- API: `/api/health/` y `/api/roles/`

`Templates/base.html` es la plantilla compartida por las páginas SGR. `static/` queda disponible para recursos propios del backend.

## Seleccionar MySQL

Configurar `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT` en el entorno. No guardar credenciales en el repositorio. El controlador MySQL y la instancia AWS se configuran por separado antes de migrar.
