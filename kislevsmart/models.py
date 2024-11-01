import logging
from venv import logger
from django.db import models, transaction
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.postgres.fields import JSONField
from datetime import timedelta
from accounts.models import ConjuntoResidencial, Usuario



# Configurar logger
logger = logging.getLogger(__name__)


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
        """Sobrescribe el método save para manejar zonas horarias"""
        if not self.pk:
            self.fecha_generacion = self.get_tiempo_actual()
            
        # Asegurar zona horaria correcta para ultima_lectura
        if self.ultima_lectura and timezone.is_naive(self.ultima_lectura):
            self.ultima_lectura = timezone.make_aware(
                self.ultima_lectura, 
                timezone.get_current_timezone()
            )
            
        super().save(*args, **kwargs)





class VisitanteVehicular(models.Model):
    """
    Modelo para visitantes con vehículo, mantiene los mismos campos que Visitante
    más los campos específicos para vehículos
    """
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
    
    # Campos adicionales para vehículos
    tipo_vehiculo = models.CharField(max_length=20, choices=[
        ('carro', 'Carro'),
        ('moto', 'Moto'),
        ('cicla', 'Cicla'),
        ('otro', 'Otro'),
    ])
    placa = models.CharField(max_length=10)
    segunda_lectura = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} - {self.placa}"

    def get_tiempo_actual(self):
        """Obtiene el tiempo actual en la zona horaria local"""
        return timezone.localtime(timezone.now())

    def get_fecha_generacion_local(self):
        """Obtiene la fecha de generación en la zona horaria local"""
        return timezone.localtime(self.fecha_generacion)

    def save(self, *args, **kwargs):
        """Sobrescribe el método save para manejar zonas horarias"""
        if not self.pk:
            self.fecha_generacion = self.get_tiempo_actual()
            
        # Asegurar zona horaria correcta para ultima_lectura y segunda_lectura
        if self.ultima_lectura and timezone.is_naive(self.ultima_lectura):
            self.ultima_lectura = timezone.make_aware(
                self.ultima_lectura, 
                timezone.get_current_timezone()
            )
            
        if self.segunda_lectura and timezone.is_naive(self.segunda_lectura):
            self.segunda_lectura = timezone.make_aware(
                self.segunda_lectura, 
                timezone.get_current_timezone()
            )
            
        super().save(*args, **kwargs)

    def esta_completado(self):
        """Verifica si el visitante ya realizó las dos lecturas"""
        return bool(self.ultima_lectura and self.segunda_lectura)

    def puede_leer(self):
        """Verifica si el QR puede ser leído nuevamente"""
        return not self.esta_completado()

    def registrar_lectura(self):
        """
        Registra una nueva lectura del QR.
        Retorna True si la lectura fue exitosa, False si ya no se permiten más lecturas
        """
        if not self.puede_leer():
            return False

        tiempo_actual = self.get_tiempo_actual()
        
        if not self.ultima_lectura:
            self.ultima_lectura = tiempo_actual
        else:
            self.segunda_lectura = tiempo_actual
            
        self.save()
        return True
















    


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
        
        
        
        

# models.py
class ParqueaderoCarro(models.Model):
    conjunto = models.ForeignKey(ConjuntoResidencial, on_delete=models.CASCADE)
    total_espacios = models.PositiveIntegerField(default=0)
    descripcion = models.TextField(blank=True, null=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Parqueadero de Carro'
        verbose_name_plural = 'Parqueaderos de Carros'

    def __str__(self):
        return f"{self.conjunto.nombre} - Total espacios carros: {self.total_espacios}"

    @classmethod
    def get_disponibilidad(cls, conjunto_id):
        """Obtiene la disponibilidad de parqueaderos de carros para un conjunto"""
        try:
            parqueadero = cls.objects.get(conjunto_id=conjunto_id)
            # Contar vehículos actualmente en el parqueadero
            ocupados = VisitanteVehicular.objects.filter(
                usuario_id=conjunto_id,  # Cambiado para usar usuario_id directamente
                tipo_vehiculo='carro',
                ultima_lectura__isnull=False,
                segunda_lectura__isnull=True
            ).count()
            
            # Registrar actividad para debugging
            print(f"Conjunto {conjunto_id}: Total={parqueadero.total_espacios}, Ocupados={ocupados}")
            
            return {
                'total': parqueadero.total_espacios,
                'ocupados': ocupados,
                'disponibles': parqueadero.total_espacios - ocupados
            }
        except cls.DoesNotExist:
            return {'total': 0, 'ocupados': 0, 'disponibles': 0}

class ParqueaderoMoto(models.Model):
    conjunto = models.ForeignKey(ConjuntoResidencial, on_delete=models.CASCADE)
    total_espacios = models.PositiveIntegerField(default=0)
    descripcion = models.TextField(blank=True, null=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Parqueadero de Moto'
        verbose_name_plural = 'Parqueaderos de Motos'

    def __str__(self):
        return f"{self.conjunto.nombre} - Total espacios motos: {self.total_espacios}"

    @classmethod
    def get_disponibilidad(cls, conjunto_id):
        """Obtiene la disponibilidad de parqueaderos de motos para un conjunto"""
        try:
            parqueadero = cls.objects.get(conjunto_id=conjunto_id)
            # Contar motos actualmente en el parqueadero
            ocupados = VisitanteVehicular.objects.filter(
                usuario_id=conjunto_id,  # Cambiado para usar usuario_id directamente
                tipo_vehiculo='moto',
                ultima_lectura__isnull=False,
                segunda_lectura__isnull=True
            ).count()
            
            # Registrar actividad para debugging
            print(f"Conjunto {conjunto_id}: Total={parqueadero.total_espacios}, Ocupados={ocupados}")
            
            return {
                'total': parqueadero.total_espacios,
                'ocupados': ocupados,
                'disponibles': parqueadero.total_espacios - ocupados
            }
        except cls.DoesNotExist:
            return {'total': 0, 'ocupados': 0, 'disponibles': 0}        



        