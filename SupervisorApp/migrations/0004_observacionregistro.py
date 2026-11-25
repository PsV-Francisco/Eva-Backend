from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('FuncionarioApp', '0010_registro_vecino'),
        ('SupervisorApp', '0003_alter_revisionevidencia_decision'),
    ]

    operations = [
        migrations.CreateModel(
            name='ObservacionRegistro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_hora', models.DateTimeField(auto_now_add=True)),
                ('comentario', models.TextField()),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='observaciones_registros', to=settings.AUTH_USER_MODEL)),
                ('evidencia', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='observaciones_cronologicas', to='SupervisorApp.evidencia')),
                ('registro', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='observaciones_cronologicas', to='FuncionarioApp.registro')),
            ],
            options={
                'verbose_name': 'observación de registro',
                'verbose_name_plural': 'observaciones de registros',
                'ordering': ['fecha_hora', 'pk'],
            },
        ),
    ]
