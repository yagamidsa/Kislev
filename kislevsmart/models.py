from django.db import models
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.postgres.fields import JSONField



class Visitante(models.Model):
    
    email_creador = models.EmailField()        # Correo electrónico del propietario
    nombre = models.CharField(max_length=100)  # Nombre del visitante
    email = models.EmailField()                # Correo electrónico del visitante
    celular = models.CharField(max_length=15)  # Número de celular del visitante
    cedula = models.CharField(max_length=20)   # Documento de identidad del visitante
    motivo = models.CharField(max_length=255)  # Motivo de la visita
    token = models.CharField(max_length=100, unique=True)  # Cambiar a CharField
    fecha_generacion = models.DateTimeField(default=timezone.now)  # Fecha de generación del token
    ultima_lectura = models.DateTimeField(null=True, blank=True)  # Fecha y hora de la última lectura del QR
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)  # Campo actualizado
    nombre_log = models.CharField(max_length=100)
    numper = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.nombre} - {self.email}"


class Sala(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    capacidad = models.IntegerField()
    imagen = models.ImageField(upload_to='salas/', null=True, blank=True)
    # Cambiamos de django.contrib.postgres.fields.JSONField al nuevo django.db.models.JSONField
    amenities = models.JSONField(default=dict, blank=True)
    estado = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'salas'
        ordering = ['nombre']
        verbose_name = 'Sala'
        verbose_name_plural = 'Salas'

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('calendario_sala', args=[str(self.id)])

class Reserva(models.Model):
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name='reservas')
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.BooleanField(default=True)
    notas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reservas'
        unique_together = ['sala', 'fecha', 'hora_inicio']
        ordering = ['-fecha', 'hora_inicio']
        verbose_name = 'Reserva'
        verbose_name_plural = 'Reservas'

    def __str__(self):
        return f"{self.sala.nombre} - {self.fecha} ({self.hora_inicio} - {self.hora_fin})"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Validar que hora_fin sea posterior a hora_inicio
        if self.hora_fin <= self.hora_inicio:
            raise ValidationError('La hora de finalización debe ser posterior a la hora de inicio')
        
        # Validar que no haya solapamiento con otras reservas
        solapadas = Reserva.objects.filter(
            sala=self.sala,
            fecha=self.fecha,
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio
        ).exclude(id=self.id)
        
        if solapadas.exists():
            raise ValidationError('Ya existe una reserva para este horario')