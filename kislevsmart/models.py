from django.db import models
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.postgres.fields import JSONField
from datetime import timedelta

class Visitante(models.Model):
    email_creador = models.EmailField()
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    celular = models.CharField(max_length=15)
    cedula = models.CharField(max_length=20)
    motivo = models.CharField(max_length=255)
    token = models.CharField(max_length=100, unique=True)
    fecha_generacion = models.DateTimeField(default=timezone.now)
    ultima_lectura = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    nombre_log = models.CharField(max_length=100)
    numper = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.nombre} - {self.email}"

    def get_tiempo_actual(self):
        """Obtiene el tiempo actual en la zona horaria local"""
        return timezone.localtime(timezone.now())

    def get_fecha_generacion_local(self):
        """Obtiene la fecha de generación en la zona horaria local"""
        return timezone.localtime(self.fecha_generacion)

    def save(self, *args, **kwargs):
        # Si es una nueva instancia (creación)
        if not self.pk:
            # Asegurar que fecha_generacion esté en la zona horaria local
            self.fecha_generacion = self.get_tiempo_actual()
        
        # Para actualizaciones, asegurar que ultima_lectura esté en la zona horaria local
        if self.ultima_lectura and timezone.is_naive(self.ultima_lectura):
            self.ultima_lectura = timezone.make_aware(self.ultima_lectura, timezone.get_current_timezone())
        
        super().save(*args, **kwargs)

    def esta_vigente(self):
        """Verifica si el QR está dentro del período de validez (24 horas)"""
        if not self.fecha_generacion:
            return False
            
        # Obtener tiempos en zona horaria local
        fecha_generacion_local = self.get_fecha_generacion_local()
        tiempo_actual_local = self.get_tiempo_actual()
        tiempo_expiracion = fecha_generacion_local + timedelta(hours=24)
        
        return tiempo_actual_local <= tiempo_expiracion

    def esta_disponible(self):
        """Verifica si el QR puede ser usado (no ha sido usado y está vigente)"""
        return self.ultima_lectura is None and self.esta_vigente()

    def registrar_lectura(self, nombre_log):
        """Registra una lectura del QR si es posible"""
        if self.esta_disponible():
            self.ultima_lectura = self.get_tiempo_actual()
            self.nombre_log = nombre_log
            self.save()
            return True
        return False

    


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