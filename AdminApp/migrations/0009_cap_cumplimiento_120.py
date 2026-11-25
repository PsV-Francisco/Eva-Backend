from django.db import migrations
from django.db.utils import OperationalError, ProgrammingError


def actualizar_tope(apps, schema_editor):
    ParametroSistema = apps.get_model("AdminApp", "ParametroSistema")
    try:
        ParametroSistema.objects.filter(
            clave__icontains="tope", valor=150
        ).update(valor=120)
    except (OperationalError, ProgrammingError):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("AdminApp", "0008_remove_comentarios_autor_and_more"),
    ]

    operations = [
        migrations.RunPython(actualizar_tope, migrations.RunPython.noop),
    ]