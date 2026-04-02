"""Tests para el módulo financiero."""
import pytest
from datetime import date, timedelta
from django.urls import reverse
from kislevsmart.models import Cuota, Pago


@pytest.mark.django_db
class TestCuotas:
    def test_crear_cuota(self, client, admin):
        client.force_login(admin)
        resp = client.post(reverse('crear_cuota'), {
            'nombre': 'Administración junio',
            'monto': 250000,
            'periodicidad': 'mensual',
            'fecha_vencimiento': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
        })
        assert resp.status_code == 200
        import json
        data = json.loads(resp.content)
        assert data['status'] == 'ok'
        assert Cuota.objects.filter(nombre='Administración junio').exists()

    def test_crear_cuota_monto_invalido(self, client, admin):
        client.force_login(admin)
        resp = client.post(reverse('crear_cuota'), {
            'nombre': 'Mala',
            'monto': 0,
            'periodicidad': 'mensual',
            'fecha_vencimiento': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
        })
        import json
        data = json.loads(resp.content)
        assert data['status'] == 'error'

    def test_crear_cuota_requiere_admin(self, client, propietario):
        """Un propietario no puede crear cuotas."""
        client.force_login(propietario)
        resp = client.post(reverse('crear_cuota'), {
            'nombre': 'Hack',
            'monto': 100000,
            'periodicidad': 'mensual',
            'fecha_vencimiento': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
        })
        assert resp.status_code == 302  # redirige al login


@pytest.mark.django_db
class TestPagos:
    def test_registrar_pago(self, client, admin, propietario, cuota):
        client.force_login(admin)
        resp = client.post(reverse('registrar_pago', args=[cuota.id]), {
            'propietario_id': propietario.id,
            'monto_pagado': cuota.monto,
            'metodo': 'transferencia',
            'comprobante': 'REF-001',
            'fecha_pago': date.today().strftime('%Y-%m-%d'),
        })
        import json
        data = json.loads(resp.content)
        assert data['status'] == 'ok'
        assert Pago.objects.filter(cuota=cuota, propietario=propietario).exists()

    def test_estado_cuenta_propietario(self, client, propietario, cuota):
        """El propietario puede ver su estado de cuenta."""
        client.force_login(propietario)
        resp = client.get(reverse('estado_cuenta'))
        assert resp.status_code == 200

    def test_estado_cuenta_requiere_propietario(self, client, portero):
        """Un portero no puede ver estado de cuenta."""
        client.force_login(portero)
        resp = client.get(reverse('estado_cuenta'))
        assert resp.status_code == 302
