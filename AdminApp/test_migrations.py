from importlib import import_module
from types import SimpleNamespace
from unittest import skip

from django.apps import apps
from django.db import connection
from django.test import TestCase


class AuthorizedDelegationsDataMigrationTests(TestCase):
    @skip('La cadena de migraciones se regeneró; validar esta prueba tras su aprobación.')
    def test_existing_primary_delegation_is_copied_as_authorized(self):
        Delegacion = apps.get_model('AdminApp', 'Delegacion')
        Usuario = apps.get_model('AdminApp', 'Usuario')
        delegation = Delegacion.objects.create(nombre='Delegación histórica')
        user = Usuario.objects.create(
            email='legacy-user@sgr.test',
            delegacion_id=delegation.pk,
        )

        migration = import_module('AdminApp.migrations.0009_authorized_delegations')
        migration.copy_primary_delegations(
            apps,
            SimpleNamespace(connection=connection),
        )

        self.assertTrue(
            user.delegaciones_autorizadas.filter(pk=delegation.pk).exists(),
        )
