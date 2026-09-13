from django.db import models
from django.utils import timezone

class Cargo(models.Model):
    nombre = models.CharField(max_length=100,verbose_name="Nombre del Cargo")
    descripcion = models.CharField(max_length=200,verbose_name="Descripción",blank=True,null=True)
    creado = models.DateTimeField(default=timezone.now,verbose_name="Fecha de Creación")

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = "cargos"
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        

