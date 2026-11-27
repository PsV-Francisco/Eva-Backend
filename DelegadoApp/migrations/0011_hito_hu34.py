# HU-34: hitos con fecha de inicio, término opcional, varios responsables
# y estado "finalizado". Se quita el vínculo obligatorio a un único registro:
# ahora son las actividades (Registro.hito) las que apuntan al hito.

import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def copiar_responsable_y_fechas(apps, schema_editor):
    Hito = apps.get_model('DelegadoApp', 'Hito')
    ahora = django.utils.timezone.now()
    for hito in Hito.objects.all():
        if hito.responsable_id:
            hito.responsables.add(hito.responsable_id)
        inicio = hito.fecha_termino if hito.fecha_termino and hito.fecha_termino < ahora else ahora
        Hito.objects.filter(pk=hito.pk).update(fecha_inicio=inicio)


class Migration(migrations.Migration):

    dependencies = [
        ("DelegadoApp", "0010_alter_historialestadocompromiso_estado_nuevo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="hito",
            name="fecha_inicio",
            field=models.DateTimeField(
                db_column="FECHA_INICIO", default=django.utils.timezone.now
            ),
        ),
        migrations.AddField(
            model_name="hito",
            name="responsables",
            field=models.ManyToManyField(
                db_table="hito_responsables",
                related_name="hitos_responsables",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copiar_responsable_y_fechas, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="hito",
            name="registro",
        ),
        migrations.RemoveField(
            model_name="hito",
            name="responsable",
        ),
        migrations.AlterModelOptions(
            name="hito",
            options={
                "ordering": ["fecha_inicio", "nombre"],
                "verbose_name": "hito",
                "verbose_name_plural": "hitos",
            },
        ),
        migrations.AlterField(
            model_name="hito",
            name="estado",
            field=models.CharField(
                choices=[
                    ("operativo", "Operativo"),
                    ("finalizado", "Finalizado"),
                    ("cancelado", "Cancelado"),
                ],
                default="operativo",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="hito",
            name="fecha_termino",
            field=models.DateTimeField(
                blank=True, db_column="FECHA_TERMINO", null=True
            ),
        ),
    ]
