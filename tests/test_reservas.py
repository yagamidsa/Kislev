"""Tests para el módulo de reservas de salas."""
import pytest
from datetime import date, time, timedelta
from django.urls import reverse
from kislevsmart.models import Reserva


@pytest.mark.django_db
class TestReservas:
    def _payload(self, sala, dias=1, h_inicio='10:00', h_fin='12:00'):
        fecha = (date.today() + timedelta(days=dias)).strftime('%Y-%m-%d')
        return {
            'fecha': fecha,
            'hora_inicio': h_inicio,
            'hora_fin': h_fin,
            'notas': 'Test',
        }

    def test_crear_reserva_exitosa(self, client, admin, sala):
        client.force_login(admin)
        resp = client.post(reverse('reservar_sala', args=[sala.id]), self._payload(sala))
        assert resp.status_code == 200
        assert Reserva.objects.filter(sala=sala).exists()

    def test_reserva_solapada_rechazada(self, client, admin, sala):
        """Dos reservas en el mismo horario: la segunda falla."""
        client.force_login(admin)
        payload = self._payload(sala)
        client.post(reverse('reservar_sala', args=[sala.id]), payload)
        resp = client.post(reverse('reservar_sala', args=[sala.id]), payload)
        assert resp.status_code == 200
        assert Reserva.objects.filter(sala=sala).count() == 1

    def test_reserva_fecha_pasada_rechazada(self, client, admin, sala):
        """No se puede reservar en el pasado."""
        client.force_login(admin)
        payload = self._payload(sala, dias=-1)
        client.post(reverse('reservar_sala', args=[sala.id]), payload)
        assert not Reserva.objects.filter(sala=sala).exists()

    def test_reserva_requiere_autenticacion(self, client, sala):
        resp = client.post(reverse('reservar_sala', args=[sala.id]), self._payload(sala))
        assert resp.status_code == 302
        assert 'login' in resp.url
