from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.test import Client
from django.urls import reverse

from AdminApp.models import Cargo, Delegacion, Historial, ParametroSistema
from AdminApp.roles import ensure_role_group
from CoordinadorApp.models import Desempeno, Item, Periodo
from CoordinadorApp.services import resumen_cumplimiento
from DelegadoApp.models import (
    Agenda,
    Ausencia,
    Compromiso,
    HistorialReasignacionCompromiso,
)
from DelegadoApp.services import resumen_delegacion, actualizar_compromiso
from FuncionarioApp.models import Registro, Subtipo, Tipo
from SupervisorApp.models import Evidencia, ObservacionRegistro


class Command(BaseCommand):
    help = 'Simula y verifica las historias HU-07, HU-15, HU-21, HU-24, HU-25, HU-29 y HU-37 sin persistir datos.'

    def add_arguments(self, parser):
        parser.add_argument('--fail-fast', action='store_true')

    def handle(self, *args, **options):
        # Client usa ``testserver``; se modifica solo la configuración en memoria.
        settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, 'testserver']
        try:
            self.stdout._out.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
        checks = []
        try:
            with transaction.atomic():
                try:
                    data = self._seed()
                    checks.append(self._check_hu07_hu25(data))
                    checks.append(self._check_hu21(data))
                    checks.append(self._check_hu15_hu24_hu29_hu37(data))
                    checks.append(self._check_repaired_routes(data))
                except Exception as exc:  # pragma: no cover - reporte del comando
                    checks.append(('Ejecución de simulación', False, self._error(exc)))
                finally:
                    transaction.set_rollback(True)
        except Exception as exc:
            checks.append(('Ejecución de transacción', False, self._error(exc)))
        finally:
            for file_name in getattr(self, '_temporary_files', set()):
                path = Path(settings.MEDIA_ROOT) / file_name
                if path.is_file():
                    path.unlink()

        self.stdout.write('Reporte de simulación (rollback garantizado):')
        for title, ok, detail in checks:
            mark = '✅' if ok else '❌'
            self.stdout.write(f'{mark} {title}: {detail}')
        if any(not ok for _, ok, _ in checks):
            raise SystemExit(1)

    @staticmethod
    def _error(exc):
        return f'{type(exc).__name__}: {exc}'

    @staticmethod
    def _set_parameter(clave, value):
        ParametroSistema.objects.update_or_create(
            clave=clave,
            defaults={'valor': Decimal(value), 'vigente_desde': date.today()},
        )

    def _seed(self):
        User = __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model()
        admin_cargo = Cargo.objects.create(nombre='TEST_SIM_ADMIN')
        delegate_cargo = Cargo.objects.create(nombre='TEST_SIM_DELEGADO')
        coordinator_cargo = Cargo.objects.create(nombre='TEST_SIM_COORDINADOR')
        employee_cargo = Cargo.objects.create(nombre='TEST_SIM_FUNCIONARIO')
        delegation = Delegacion.objects.create(nombre='TEST_SIM_DELEGACION')

        admin = User.objects.create_user(email='TEST_SIM_admin@example.test', password='test-pass')
        delegate = User.objects.create_user(email='TEST_SIM_delegate@example.test', password='test-pass')
        coordinator = User.objects.create_user(email='TEST_SIM_coordinator@example.test', password='test-pass')
        high = User.objects.create_user(email='TEST_SIM_high@example.test', password='test-pass')
        low = User.objects.create_user(email='TEST_SIM_low@example.test', password='test-pass')
        for user, cargo in (
            (admin, admin_cargo), (delegate, delegate_cargo),
            (coordinator, coordinator_cargo), (high, employee_cargo), (low, employee_cargo),
        ):
            from AdminApp.models import UsuarioCargo, UsuarioDelegacion
            UsuarioCargo.objects.create(usuario=user, cargo=cargo)
            if user in (delegate, high, low):
                UsuarioDelegacion.objects.create(usuario=user, delegacion=delegation)

        # The access helper recognizes these names as the built-in roles.
        admin_cargo.nombre = 'administrador'; admin_cargo.save(update_fields=['nombre'])
        delegate_cargo.nombre = 'delegado'; delegate_cargo.save(update_fields=['nombre'])
        coordinator_cargo.nombre = 'coordinador'; coordinator_cargo.save(update_fields=['nombre'])
        employee_cargo.nombre = 'funcionario'; employee_cargo.save(update_fields=['nombre'])

        for key, value in (
            (ParametroSistema.Clave.UMBRAL_ROJO, 60),
            (ParametroSistema.Clave.UMBRAL_AMBAR, 80),
            (ParametroSistema.Clave.TOPE_CUMPLIMIENTO, 120),
            (ParametroSistema.Clave.UMBRAL_DELEGACION, 80),
        ):
            self._set_parameter(key, value)

        closed = Periodo.objects.create(
            nombre='TEST_SIM_CERRADO', fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 1, 31), estado=Periodo.Estado.CERRADO,
        )
        open_period = Periodo.objects.create(
            nombre='TEST_SIM_ABIERTO', fecha_inicio=date(2026, 2, 1),
            fecha_fin=date(2026, 2, 28), estado=Periodo.Estado.ABIERTO,
        )
        item = Item.objects.create(nombre='TEST_SIM_ITEM')
        closed_performance = Desempeno.objects.create(
            usuario=high, item=item, periodo=closed, meta=1, ponderacion=100,
        )
        open_performance = Desempeno.objects.create(
            usuario=high, item=item, periodo=open_period, meta=1, ponderacion=100,
        )

        tipo = Tipo.objects.create(nombre='TEST_SIM_TIPO')
        subtipo = Subtipo.objects.create(nombre='TEST_SIM_SUBTIPO', tipo=tipo)
        agenda = Agenda.objects.create(delegacion=delegation, periodo=open_period)
        commitment = Compromiso.objects.create(
            agenda=agenda, descripcion='TEST_SIM_COMPROMISO', tipo=tipo,
            subtipo=subtipo, fecha_solicitud='2026-02-05T09:00:00Z',
            fecha_compromiso='2026-02-06T09:00:00Z',
        )
        commitment.responsable.add(delegate)
        return locals()

    def _check_hu07_hu25(self, data):
        self._set_parameter(ParametroSistema.Clave.UMBRAL_AMBAR, 85)
        self._set_parameter(ParametroSistema.Clave.TOPE_CUMPLIMIENTO, 110)
        closed_result = resumen_cumplimiento(
            [data['closed_performance']], counts={(data['high'].pk, data['item'].pk, data['closed'].pk): Decimal('2')},
            hoy=date(2026, 1, 31),
        )
        open_result = resumen_cumplimiento(
            [data['open_performance']], counts={(data['high'].pk, data['item'].pk, data['open_period'].pk): Decimal('2')},
            hoy=date(2026, 2, 28),
        )
        ok = (
            closed_result['items'][0]['cumplimiento'] == Decimal('120.00')
            and open_result['items'][0]['cumplimiento'] == Decimal('110.00')
            and data['closed'].semaforo_ambar == Decimal('80.00')
            and data['closed'].tope_cumplimiento == Decimal('120.00')
        )
        return ('HU-07/HU-25 — tope y congelamiento', ok, 'cerrado=120%, abierto=110%, snapshot intacto')

    def _check_hu21(self, data):
        low_performance = Desempeno.objects.create(
            usuario=data['low'], item=data['item'], periodo=data['open_period'],
            meta=2, ponderacion=100,
        )
        evidence = Evidencia.objects.create(
            archivo=SimpleUploadedFile('TEST_SIM.txt', b'test'),
            estado=Evidencia.Estado.APROBADA,
        )
        self._temporary_files = getattr(self, '_temporary_files', set())
        self._temporary_files.add(evidence.archivo.name)
        Registro.objects.create(
            fecha=date(2026, 2, 5), item=data['item'], periodo=data['open_period'],
            descripcion='TEST_SIM_ACTIVIDAD', autor=data['high'], tipo=data['tipo'],
            subtipo=data['subtipo'], estado=Registro.Estado.VALIDADA, evidencia=evidence,
        )
        result = resumen_delegacion(delegation=data['delegation'], period=data['open_period'])
        alerts = result['below_threshold']
        ok = len(alerts) == 1 and alerts[0]['usuario'].pk == data['low'].pk and result['cantidad_bajo_umbral'] == 1
        return ('HU-21 — alertas de bajo cumplimiento', ok, f'alertas={len(alerts)}, ordenadas por cumplimiento')

    def _check_hu15_hu24_hu29_hu37(self, data):
        actualizar_compromiso(
            compromiso=data['commitment'], autor=data['delegate'],
            responsables=[data['low']], motivo='TEST_SIM_REASIGNACION',
        )
        registro = Registro.objects.create(
            fecha=date(2026, 2, 10), item=data['item'], periodo=data['open_period'],
            descripcion='TEST_SIM_OBSERVABLE', autor=data['low'], tipo=data['tipo'],
            subtipo=data['subtipo'],
        )
        ObservacionRegistro.objects.create(registro=registro, autor=data['delegate'], comentario='TEST_SIM_OBSERVACION')
        Ausencia.objects.create(
            fecha='2026-02-12T00:00:00Z', fecha_inicio=date(2026, 2, 12),
            fecha_fin=date(2026, 2, 13), tipo=Ausencia.Tipo.OTRA_JUSTIFICADA,
            descripcion='TEST_SIM_JUSTIFICADA', desempeno=data['open_performance'],
            usuario=data['high'], item=data['item'], periodo=data['open_period'],
        )
        for index in range(26):
            Historial.objects.create(
                autor=data['admin'], accion=f'TEST_SIM_AUDIT_{index}',
                periodo=data['open_period'], entidad_afectada='TEST_SIM',
            )
        client = Client()
        client.force_login(data['admin'])
        paths = [
            reverse('administracion:historial') + '?page=2',
            reverse('administracion:ausencias') + '?page=2',
            reverse('administracion:compromisos') + '?page=2',
        ]
        responses = [client.get(path).status_code for path in paths]
        ok = (
            HistorialReasignacionCompromiso.objects.filter(compromiso=data['commitment']).exists()
            and registro.observaciones_cronologicas.count() == 1
            and Ausencia.objects.filter(usuario=data['high'], periodo=data['open_period']).exists()
            and responses == [200, 200, 200]
        )
        return ('HU-15/HU-24/HU-29/HU-37 — historial, observaciones, paginación y ausencia', ok, f'HTTP={responses}')

    def _check_repaired_routes(self, data):
        client = Client()
        cases = ((data['admin'], 'administracion:compromisos'), (data['coordinator'], 'coordinador:solicitudes_autorizacion'))
        statuses = []
        for user, name in cases:
            client.force_login(user)
            statuses.append(client.get(reverse(name)).status_code)
        ok = statuses == [200, 200]
        return ('Rutas reparadas — compromisos y solicitudes', ok, f'HTTP={statuses}')
