from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MaintainerDataMigrationTests(TransactionTestCase):
    migrate_from = [
        ('AdminApp', '0010_alter_passwordresetauditevent_action_and_more'),
        ('CoordinadorApp', '0003_alter_periodo_estado'),
        ('FuncionarioApp', '0006_alter_gestionatencion_codigo'),
    ]
    migrate_to = [
        (
            'AdminApp',
            '0011_tipoatencion_delegacion_codigo_delegacion_comuna_and_more',
        ),
        ('CoordinadorApp', '0004_item_codigo_item_estado'),
        ('FuncionarioApp', '0006_alter_gestionatencion_codigo'),
    ]

    def setUp(self):
        MigrationExecutor(connection).migrate(self.migrate_from)
        old_apps = MigrationExecutor(connection).loader.project_state(
            self.migrate_from,
        ).apps
        Delegacion = old_apps.get_model('AdminApp', 'Delegacion')
        Catalogo = old_apps.get_model('AdminApp', 'Catalogo')
        Usuario = old_apps.get_model('AdminApp', 'Usuario')
        AtencionSocial = old_apps.get_model('FuncionarioApp', 'AtencionSocial')
        Funcion = old_apps.get_model('CoordinadorApp', 'Funcion')
        Item = old_apps.get_model('CoordinadorApp', 'Item')

        delegation = Delegacion.objects.create(nombre='Delegación histórica C')
        user = Usuario.objects.create(
            email='historico-c@sgr.test',
            password='!',
        )
        Catalogo.objects.create(
            tipo='Orientación',
            subtipo='Social',
        )
        attention = AtencionSocial.objects.create(
            usuario_id=user.pk,
            tipo_atencion='Orientación',
            fecha=date(2026, 1, 2),
        )
        function = Funcion.objects.create(nombre='Función histórica')
        item = Item.objects.create(
            funcion_id=function.pk,
            nombre='Ítem histórico',
        )
        self.delegation_id = delegation.pk
        self.attention_id = attention.pk
        self.item_id = item.pk

        MigrationExecutor(connection).migrate(self.migrate_to)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_codes_and_legacy_attention_values_are_preserved(self):
        apps = MigrationExecutor(connection).loader.project_state(
            self.migrate_to,
        ).apps
        Delegacion = apps.get_model('AdminApp', 'Delegacion')
        TipoAtencion = apps.get_model('AdminApp', 'TipoAtencion')
        SubAtencion = apps.get_model('AdminApp', 'SubAtencion')
        Catalogo = apps.get_model('AdminApp', 'Catalogo')
        AtencionSocial = apps.get_model('FuncionarioApp', 'AtencionSocial')
        Item = apps.get_model('CoordinadorApp', 'Item')

        delegation = Delegacion.objects.get(pk=self.delegation_id)
        self.assertEqual(delegation.codigo, f'DEL-{delegation.pk:04d}')
        item = Item.objects.get(pk=self.item_id)
        self.assertEqual(item.codigo, f'ITEM-{item.pk:04d}')
        self.assertTrue(
            TipoAtencion.objects.filter(nombre='Orientación').exists(),
        )
        attention_type = TipoAtencion.objects.get(nombre='Orientación')
        self.assertTrue(
            SubAtencion.objects.filter(
                tipo_atencion_id=attention_type.pk,
                nombre='Social',
            ).exists(),
        )
        self.assertEqual(
            AtencionSocial.objects.get(pk=self.attention_id).tipo_atencion,
            'Orientación',
        )
        catalog = Catalogo.objects.get(tipo='Orientación')
        self.assertEqual(catalog.subtipo, 'Social')
