import os
from django.core.asgi import get_asgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings') #Aquí arreglé la ruta
application = get_asgi_application()
