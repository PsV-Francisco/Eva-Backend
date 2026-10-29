import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
TEMPLATES_DIR = BASE_DIR / 'templates'
LEGACY_TEMPLATES_DIR = BASE_DIR / 'Templates'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'La variable DJANGO_SECRET_KEY es obligatoria. '
        'Configúrala en el entorno o en el archivo .env antes de iniciar SGR.'
    )
DEBUG = os.environ.get('DEBUG','False') == 'True'
default_allowed_hosts = (
    'localhost,127.0.0.1' if DEBUG else '3.228.118.5'
)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'ALLOWED_HOSTS', default_allowed_hosts
    ).split(',')
    if host.strip()
]
default_csrf_trusted_origins = 'http://3.228.118.5,https://3.228.118.5'
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'CSRF_TRUSTED_ORIGINS', default_csrf_trusted_origins,
    ).split(',')
    if origin.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'FuncionarioApp',
    'SupervisorApp',
    'DelegadoApp',
    'CoordinadorApp',
    'AdminApp',
    'VistaFApp',
]
AUTH_USER_MODEL = 'AdminApp.Usuario'
LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/inicio/'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATES_DIR, LEGACY_TEMPLATES_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.common_header',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = os.environ.get('DB_ENGINE', 'sqlite').strip().lower()

if DB_ENGINE == 'mysql':
    required_database_settings = ('DB_NAME', 'DB_USER')
    missing_database_settings = [
        name for name in required_database_settings if not os.environ.get(name)
    ]
    if missing_database_settings:
        raise ImproperlyConfigured(
            'Configura las variables de entorno: '
            + ', '.join(missing_database_settings)
        )
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ['DB_NAME'],
            'USER': os.environ['DB_USER'],
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': (
                    "SET SESSION sql_mode='STRICT_TRANS_TABLES', "
                    'SESSION default_storage_engine=InnoDB'
                ),
            },
        }
    }
elif DB_ENGINE == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    raise ImproperlyConfigured(
        "DB_ENGINE debe ser 'sqlite' o 'mysql'."
    )

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = (
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').strip().lower() in {
    '1', 'true', 'yes', 'on',
}
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', 'SGR <no-reply@localhost>'
)

PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))
PASSWORD_RESET_RATE_LIMIT = int(os.environ.get('PASSWORD_RESET_RATE_LIMIT', '5'))
PASSWORD_RESET_RATE_WINDOW = int(
    os.environ.get('PASSWORD_RESET_RATE_WINDOW', '3600')
)
PASSWORD_RESET_CODE_TTL_SECONDS = int(
    os.environ.get('PASSWORD_RESET_CODE_TTL_SECONDS', '600')
)
PASSWORD_RESET_CODE_RESEND_SECONDS = int(
    os.environ.get('PASSWORD_RESET_CODE_RESEND_SECONDS', '45')
)
PASSWORD_RESET_CODE_MAX_ATTEMPTS = int(
    os.environ.get('PASSWORD_RESET_CODE_MAX_ATTEMPTS', '5')
)
PASSWORD_RESET_DOMAIN = os.environ.get(
    'PASSWORD_RESET_DOMAIN', '3.228.118.5'
).strip()
PASSWORD_RESET_PROTOCOL = os.environ.get(
    'PASSWORD_RESET_PROTOCOL', 'http'
).strip().lower()
if PASSWORD_RESET_PROTOCOL not in {'http', 'https'}:
    raise ImproperlyConfigured(
        'PASSWORD_RESET_PROTOCOL debe ser http o https.'
    )
if not PASSWORD_RESET_DOMAIN or '://' in PASSWORD_RESET_DOMAIN:
    raise ImproperlyConfigured(
        'PASSWORD_RESET_DOMAIN debe contener solo el dominio público, sin protocolo.'
    )
