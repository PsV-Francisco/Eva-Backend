# Evidencias técnicas del proyecto

## 1. Descripción general

Este proyecto corresponde a un sitio web desarrollado en Django para mostrar contenidos relacionados con La Serena y su entorno comunal. El sistema está estructurado en varias aplicaciones y usa Bootstrap para una presentación moderna y responsiva. La información principal se carga desde archivos JSON ubicados en la carpeta static/data, evitando el uso de bases de datos para los contenidos informativos del proyecto.

El proyecto incluye:
- Inicio y presentación general del proyecto.
- Noticias de la comuna.
- Turismo regional.
- Guía ciudadana con servicios e información útil para la comunidad.
- Lugares de servicios públicos de la ciudad.

La configuración central del proyecto se maneja desde config/settings.py y config/urls.py, donde se registran las rutas y las aplicaciones activas.

## 2. Estructura de carpetas del proyecto

```text
Eva-Backend/
├── app_inicio/
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   └── migrations/
│       └── __init__.py
├── app_noticias/
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   └── migrations/
│       └── __init__.py
├── app_servicios/
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   └── tests.py
├── app_turismo/
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   └── migrations/
│       └── __init__.py
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── static/
│   ├── css/
│   ├── data/
│   │   ├── equipo.json
│   │   ├── noticias.json
│   │   ├── turismo.json
│   │   ├── servicios_comunales.json
│   │   └── lugares_servicios.json
│   ├── img/
│   └── js/
├── templates/
│   ├── base.html
│   ├── app_inicio/
│   │   ├── about.html
│   │   └── inicio.html
│   ├── app_noticias/
│   │   ├── detalle_noticia.html
│   │   └── lista_noticias.html
│   ├── app_servicios/
│   │   ├── guia_ciudadana.html
│   │   └── lugares_servicios.html
│   └── app_turismo/
│       └── turismo.html
├── db.sqlite3
├── manage.py
├── .gitignore
└── EVIDENCIA_TECNICA_PROYECTO.md
```

## 3. Evidencia del uso de IA

A continuación se registran los prompts entregados durante la interacción con el asistente para demostrar el uso de IA en la construcción del proyecto.

### Prompt 1
"Contexto : Eres un encargado de informática de la municipalidad de la serena, el cual debe administrar un sitio web que muestra las noticias de la comuna y el turismo relacionado. Tarea : Debes crear una página con tema informativo relacionado con la comuna. Limitaciones : No debe ser algo de turismo ni de noticias de la comuna, debe ser una página informativa sobre algo relevante para la gente de la comuna, la información no debe ser extraida desde una base de datos, solo puedes obtener información creando un archivo JSON ubicado en la carpeta static/data, debes crear estaaa pagina dentro de una app de django, para acceder a esta pagina debes asignar un enlace con diseño creativo dentro de la barra de navegación principal hacia esta nueva página, la página en sí debe usar bootstrap para mostrar la información, utilizando un diseño moderno y responsivo."

### Prompt 2
"Tarea : Agrega el hipervínculo de la página 'app_servicios' al pie de página con un hipervínculo. Limitaciones : Haz que en el hipervínculo al pasar el mouse por encima cambie de color, en caso de requerir nuevas librerías explica la utilización de esta misma para su incorporación."

### Prompt 3
"Rol : Eres un periodista especializado en la redacción de documentos intuitivos. Tarea : Amplía la descripción de la página 'about.html' Limitaciones : Toma toda la información de las otras páginas y resúmelas, posteriormente la ingresas en el 'acerca de', utilizando un dashboard con bloques que contengan la información resumida de las páginas, el lenguaje debe ser intuitivo pero descriptivo."

### Prompt 4
"Tarea : (1) Explica de forma breve cuál es el uso de las clases 'AppServiciosConfig','AppNoticiasConfig','AppInicioConfig' y 'AppTurismoConfig' en el programa de Django. (2) Crea un nuevo template en la 'app_servicios' con información relacionada a los lugares de servicios públicos que se ofrecen en la ciudad. Limitaciones : (1) El nuevo template debe obtener información solo mediante un archivo JSON, su diseño debe ser moderno y responsivo, no olvides agregar interactividad con botones o títulos al pasar el mouse por encima."

### Prompt 5
"Tarea : Elimina el uso de clases como AppConfig de momento, si surge un error, corrígelo."

## 4. Respuestas obtenidas

### Respuesta al Prompt 1
Se creó la nueva aplicación app_servicios, con una vista que lee información desde un archivo JSON y una plantilla moderna con Bootstrap. Además, se añadió un enlace creativo en la navegación principal y se configuró la ruta en config/urls.py. La información utilizada quedó almacenada en static/data/servicios_comunales.json.

### Respuesta al Prompt 2
Se agregó el enlace de la página Guía ciudadana en el pie de página. Se incorporó un estilo CSS para que el hipervínculo cambie de color al pasar el mouse, usando Bootstrap ya existente y sin instalar librerías adicionales.

### Respuesta al Prompt 3
Se actualizó la vista about.html con un dashboard en bloques, resumiendo la información de inicio, noticias, turismo y guía ciudadana. El contenido fue redactado de forma más clara y descriptiva, manteniendo una estructura moderna y legible.

### Respuesta al Prompt 4
Se explicó el propósito general de las clases AppConfig en Django y se generó un nuevo template dentro de app_servicios para mostrar lugares de servicios públicos. La información fue cargada desde un archivo JSON llamado lugares_servicios.json y se agregaron efectos hover sobre las tarjetas para mejorar la interactividad.

### Respuesta al Prompt 5
Se retiraron las clases AppConfig personalizadas para las aplicaciones y se verificó que Django siguiera funcionando correctamente. Cuando apareció un problema de importación en URLs de otras apps, se corrigió utilizando importaciones relativas desde . import views, y se validó con Django check y pruebas del proyecto.

## Verificación técnica

Durante el proceso se ejecutaron comprobaciones de integridad del proyecto, incluyendo:
- python manage.py check
- python manage.py test

Estas validaciones fueron utilizadas para confirmar que la aplicación siguiera funcionando tras cada ajuste realizado.
