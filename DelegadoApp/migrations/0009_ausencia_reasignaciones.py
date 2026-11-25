from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('CoordinadorApp', '0012_gestionatencion_nombre'),
        ('DelegadoApp', '0008_alter_compromiso_estado'),
    ]

    operations = [
        migrations.AddField(
            model_name='ausencia',
            name='tipo',
            field=models.CharField(choices=[('dias_libres', 'Días libres'), ('vacaciones', 'Vacaciones'), ('dias_administrativos', 'Días administrativos'), ('licencias', 'Licencias'), ('otra_justificada', 'Otra ausencia justificada')], db_column='TIPO', default='otra_justificada', max_length=32),
        ),
        migrations.AddField(
            model_name='ausencia',
            name='fecha_inicio',
            field=models.DateField(blank=True, db_column='FECHA_INICIO', null=True),
        ),
        migrations.AddField(
            model_name='ausencia',
            name='fecha_fin',
            field=models.DateField(blank=True, db_column='FECHA_FIN', null=True),
        ),
        migrations.CreateModel(
            name='HistorialReasignacionCompromiso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsables_anteriores', models.JSONField(default=list)),
                ('responsables_nuevos', models.JSONField(default=list)),
                ('fecha_hora', models.DateTimeField(auto_now_add=True)),
                ('motivo', models.TextField()),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reasignaciones_compromisos', to=settings.AUTH_USER_MODEL)),
                ('compromiso', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial_reasignaciones', to='DelegadoApp.compromiso')),
            ],
            options={
                'verbose_name': 'historial de reasignación de compromiso',
                'verbose_name_plural': 'historiales de reasignación de compromisos',
                'ordering': ['-fecha_hora'],
            },
        ),
    ]
