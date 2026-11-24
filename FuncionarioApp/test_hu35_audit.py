from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from AdminApp.audit import registrar_historial
from AdminApp.models import Cargo, Historial
from FuncionarioApp.models import (
    Registro,
    WEEKLY_CLOSURE_MESSAGE,
    fecha_cierre_semanal,
    periodo_semanal_abierto,
)
from test_helpers import create_user


class WeeklyClosureTests(TestCase):
    def test_monday_deadline_is_open_and_tuesday_is_closed(self):
        activity_date = date(2026, 3, 2)
        deadline = fecha_cierre_semanal(activity_date)

        self.assertEqual(deadline.date(), date(2026, 3, 9))
        self.assertTrue(periodo_semanal_abierto(
            activity_date,
            deadline,
        ))
        self.assertFalse(periodo_semanal_abierto(
            activity_date,
            deadline + timedelta(microseconds=1),
        ))

    def test_weekly_deadline_crosses_year_boundary(self):
        activity_date = date(2026, 12, 28)
        deadline = fecha_cierre_semanal(activity_date)

        self.assertEqual(deadline.date(), date(2027, 1, 4))
        self.assertTrue(periodo_semanal_abierto(activity_date, deadline))

    def test_registro_clean_uses_uniform_closure_message(self):
        activity_date = date(2026, 3, 2)
        deadline = fecha_cierre_semanal(activity_date)
        registro = Registro(fecha=activity_date)

        with self.assertRaisesMessage(
            ValidationError,
            WEEKLY_CLOSURE_MESSAGE,
        ):
            with timezone.override(timezone.get_current_timezone()):
                with self._patched_now(deadline + timedelta(microseconds=1)):
                    registro.clean()

    class _patched_now:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            self.original = timezone.now
            timezone.now = lambda: self.value

        def __exit__(self, exc_type, exc_value, traceback):
            timezone.now = self.original


class ImmutableAuditTests(TestCase):
    def setUp(self):
        self.user = create_user(
            email='audit-immutable@example.com',
            password='Sgr-Test-Password-418!',
            cargo=Cargo.objects.create(nombre='admin'),
        )
        self.entry = registrar_historial(
            actor=self.user,
            action='Prueba de auditoría',
            entity='Registro:1',
            before={'fecha': date(2026, 3, 2)},
            after={'fecha': datetime(2026, 3, 3)},
        )

    def test_existing_audit_entry_cannot_be_saved_or_deleted(self):
        self.entry.accion = 'Intento de modificación'
        with self.assertRaisesMessage(ValidationError, 'inmutables'):
            self.entry.save()
        with self.assertRaisesMessage(ValidationError, 'no se pueden eliminar'):
            self.entry.delete()

    def test_audit_snapshots_are_stored_as_json_safe_values(self):
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.valor_anterior, {'fecha': '2026-03-02'})
        self.assertEqual(self.entry.valor_nuevo, {'fecha': '2026-03-03T00:00:00'})
