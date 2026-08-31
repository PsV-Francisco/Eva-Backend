import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings') #Aquí arreglé la ruta de la configuración
application = get_wsgi_application()
