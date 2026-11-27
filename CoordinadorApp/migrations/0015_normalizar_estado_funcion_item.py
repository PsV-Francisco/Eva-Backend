from django.db import migrations


def normalizar_estado(apps, schema_editor):
    """Deja el estado de funciones e ítems en minúsculas y sin espacios.

    En producción había valores como 'Activo' que MariaDB acepta en los
    filtros pero Python no reconoce al comparar (ej. 'activo' != 'Activo').
    Se pasa por un valor intermedio porque MariaDB compara sin distinguir
    mayúsculas y podría no escribir un cambio que solo afecta a mayúsculas.
    """
    for model_name in ('Funcion', 'Item'):
        Model = apps.get_model('CoordinadorApp', model_name)
        for pk, estado in Model.objects.values_list('pk', 'estado'):
            normalizado = (estado or '').strip().lower() or 'activo'
            if normalizado != estado:
                Model.objects.filter(pk=pk).update(estado='tmp')
                Model.objects.filter(pk=pk).update(estado=normalizado)


class Migration(migrations.Migration):

    dependencies = [
        ('CoordinadorApp', '0014_normalizar_estado_periodo'),
    ]

    operations = [
        migrations.RunPython(normalizar_estado, migrations.RunPython.noop),
    ]
