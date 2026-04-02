"""Tests para creación y validación de visitantes / QR."""
import uuid
import pytest
from django.urls import reverse
from cryptography.fernet import Fernet
from django.conf import settings
from kislevsmart.models import Visitante


@pytest.mark.django_db
class TestCrearVisitante:
    def test_crear_visitante_peatonal(self, client, admin):
        """El portero puede crear un visitante peatonal."""
        client.force_login(admin)
        resp = client.post(reverse('bienvenida'), {
            'tipo_visitante': 'peatonal',
            'nombre': 'María López',
            'email': 'maria@test.com',
            'celular': '3109876543',
            'cedula': '55555555',
            'motivo': 'Entrega',
            'numper': '101',
            'nombre_log': admin.email,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code in (200, 302)
        assert Visitante.objects.filter(cedula='55555555').exists()

    def test_visitante_requiere_autenticacion(self, client):
        """Sin login, bienvenida redirige al login."""
        resp = client.get(reverse('bienvenida'))
        assert resp.status_code == 302
        assert 'login' in resp.url


@pytest.mark.django_db
class TestValidarQR:
    def _generar_token_cifrado(self, tipo, token_uuid):
        cipher = Fernet(settings.FERNET_KEY.encode())
        raw = f"Kislev_{tipo}_{token_uuid}"
        return cipher.encrypt(raw.encode()).decode()

    def test_qr_sin_source_scan_rechazado(self, client, portero, visitante):
        """QR accedido sin ?source=scan muestra error."""
        client.force_login(portero)
        token_enc = self._generar_token_cifrado('peatonal', visitante.token)
        resp = client.get(reverse('validar_qr', args=[token_enc]))
        assert resp.status_code == 200
        assert 'Acceso no autorizado' in resp.content.decode()

    def test_qr_invalido_token_basura(self, client, portero):
        """Token que no se puede descifrar muestra error."""
        client.force_login(portero)
        resp = client.get(reverse('validar_qr', args=['tokenbasura']), {'source': 'scan'})
        assert resp.status_code in (200, 404)

    def test_qr_peatonal_primera_lectura(self, client, portero, visitante):
        """Primera lectura de QR peatonal registra ultima_lectura."""
        client.force_login(portero)
        token_enc = self._generar_token_cifrado('peatonal', visitante.token)
        resp = client.get(reverse('validar_qr', args=[token_enc]), {'source': 'scan'})
        assert resp.status_code in (200, 302)
        visitante.refresh_from_db()
        assert visitante.ultima_lectura is not None
