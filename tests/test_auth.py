"""Tests para flujo de autenticación."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestLogin:
    def test_login_exitoso_un_conjunto(self, client, admin):
        """Un usuario con un solo conjunto inicia sesión directamente."""
        url = reverse('accounts:login')
        resp = client.post(url, {'cedula': '11111111', 'password': 'adminpass123'})
        assert resp.status_code == 302
        assert resp.url != url  # redirige al panel

    def test_login_password_incorrecta(self, client, admin):
        """Contraseña incorrecta muestra error."""
        url = reverse('accounts:login')
        resp = client.post(url, {'cedula': '11111111', 'password': 'wrongpass'})
        assert resp.status_code == 200
        assert 'Contraseña incorrecta' in resp.content.decode()

    def test_login_cedula_inexistente(self, client, db):
        """Cédula que no existe muestra error."""
        url = reverse('accounts:login')
        resp = client.post(url, {'cedula': '99999999', 'password': 'cualquier'})
        assert resp.status_code == 200
        assert 'No existe' in resp.content.decode()

    def test_get_login_redirige_si_autenticado(self, client, admin):
        """Un usuario ya autenticado que visita /login es redirigido."""
        client.force_login(admin)
        resp = client.get(reverse('accounts:login'))
        assert resp.status_code == 302

    def test_logout(self, client, admin):
        """El logout termina la sesión."""
        client.force_login(admin)
        resp = client.post(reverse('accounts:logout'))
        assert resp.status_code == 302
        # Después del logout, dashboard debe redirigir al login
        resp2 = client.get(reverse('dashboard'))
        assert resp2.status_code == 302
