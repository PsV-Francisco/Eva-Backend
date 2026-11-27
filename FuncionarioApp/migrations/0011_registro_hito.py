# HU-34: actividades asociadas a un hito.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("DelegadoApp", "0011_hito_hu34"),
        ("FuncionarioApp", "0010_registro_vecino"),
    ]

    operations = [
        migrations.AddField(
            model_name="registro",
            name="hito",
            field=models.ForeignKey(
                blank=True,
                db_column="HITO",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="actividades",
                to="DelegadoApp.hito",
            ),
        ),
    ]
