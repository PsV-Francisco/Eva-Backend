from django.db import migrations


def normalizar_estado_periodo(apps, schema_editor):
    """HU-28: deja el estado de cada período en minúsculas ('Abierto' -> 'abierto').

    Se pasa por un valor intermedio porque MariaDB compara sin distinguir
    mayúsculas y podría no escribir un cambio que solo afecta a mayúsculas.
    """
    Periodo = apps.get_model('CoordinadorApp', 'Periodo')
    for pk, estado in Periodo.objects.values_list('pk', 'estado'):
        normalizado = (estado or '').strip().lower() or 'abierto'
        if normalizado != estado:
            Periodo.objects.filter(pk=pk).update(estado='tmp')
            Periodo.objects.filter(pk=pk).update(estado=normalizado)


class Migration(migrations.Migration):

    dependencies = [
        ('CoordinadorApp', '0013_periodo_semaforo_ambar_periodo_semaforo_rojo_and_more'),
    ]

    operations = [
        migrations.RunPython(normalizar_estado_periodo, migrations.RunPython.noop),
    ]
