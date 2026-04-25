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
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='usuario_id'
    )
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

    class Meta:
        indexes = [
            models.Index(fields=['email_creador'], name='vis_email_creador_idx'),
            models.Index(fields=['fecha_generacion'], name='vis_fecha_gen_idx'),
        ]



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
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='usuario_id'
    )
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

    class Meta:
        indexes = [
            models.Index(fields=['email_creador'], name='visveh_email_creador_idx'),
            models.Index(fields=['fecha_generacion'], name='visveh_fecha_gen_idx'),
            models.Index(fields=['conjunto', 'ultima_lectura'], name='visveh_conj_ulect_idx'),
        ]

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


class VisitanteGuardado(models.Model):
    """Contactos frecuentes de un propietario para generar QR rápidamente."""
    email_propietario = models.EmailField(db_index=True)
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    nombre      = models.CharField(max_length=100)
    email       = models.EmailField()
    celular     = models.CharField(max_length=15)
    cedula      = models.CharField(max_length=20)
    motivo      = models.CharField(max_length=255, blank=True)
    numper      = models.CharField(max_length=20, default='1')
    tipo        = models.CharField(max_length=20, choices=[
        ('peatonal',  'Peatonal'),
        ('vehicular', 'Vehicular'),
    ], default='peatonal')
    tipo_vehiculo = models.CharField(max_length=20, blank=True)
    placa         = models.CharField(max_length=10, blank=True)
    creado        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Visitante Guardado'
        verbose_name_plural = 'Visitantes Guardados'

    def __str__(self):
        return f"{self.nombre} ({self.tipo}) — {self.email_propietario}"
















    


class Sala(models.Model):
    conjunto = models.ForeignKey('accounts.ConjuntoResidencial', on_delete=models.CASCADE, null=True, blank=True)
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
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('aprobada', 'Aprobada'),
        ('rechazada', 'Rechazada'),
        ('cancelada', 'Cancelada'),
    ]
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name='reservas')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservas'
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=15, choices=ESTADOS, default='pendiente')
    notas = models.TextField(blank=True)
    aprobada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservas_aprobadas'
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    motivo_rechazo = models.CharField(max_length=255, blank=True)
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
        if self.hora_fin <= self.hora_inicio:
            raise ValidationError('La hora de finalización debe ser posterior a la hora de inicio')
        solapadas = Reserva.objects.filter(
            sala=self.sala, fecha=self.fecha,
            hora_inicio__lt=self.hora_fin, hora_fin__gt=self.hora_inicio,
            estado__in=['pendiente', 'aprobada']
        ).exclude(id=self.id if self.id else 0)
        if solapadas.exists():
            raise ValidationError('Ya existe una reserva para ese horario')


class BloqueoSala(models.Model):
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name='bloqueos')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    motivo = models.CharField(max_length=255, default='Mantenimiento')
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='bloqueos_sala'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_inicio']
        verbose_name = 'Bloqueo de Sala'
        verbose_name_plural = 'Bloqueos de Salas'

    def __str__(self):
        return f"{self.sala.nombre} — {self.fecha_inicio} a {self.fecha_fin}"

    def activo_en(self, fecha):
        return self.fecha_inicio <= fecha <= self.fecha_fin


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
                conjunto_id=conjunto_id,
                tipo_vehiculo='carro',
                ultima_lectura__isnull=False,
                segunda_lectura__isnull=True
            ).count()
            logger.debug(f"Disponibilidad carros conjunto {conjunto_id}: Total={parqueadero.total_espacios}, Ocupados={ocupados}")
            
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
                conjunto_id=conjunto_id,
                tipo_vehiculo='moto',
                ultima_lectura__isnull=False,
                segunda_lectura__isnull=True
            ).count()
            logger.debug(f"Disponibilidad motos conjunto {conjunto_id}: Total={parqueadero.total_espacios}, Ocupados={ocupados}")

            return {
                'total': parqueadero.total_espacios,
                'ocupados': ocupados,
                'disponibles': parqueadero.total_espacios - ocupados
            }
        except cls.DoesNotExist:
            return {'total': 0, 'ocupados': 0, 'disponibles': 0}


class Cuota(models.Model):
    PERIODICIDAD = [
        ('mensual', 'Mensual'),
        ('trimestral', 'Trimestral'),
        ('anual', 'Anual'),
        ('extraordinaria', 'Extraordinaria'),
    ]

    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        related_name='cuotas'
    )
    nombre = models.CharField(max_length=100, help_text="Ej: Administración mayo 2026")
    descripcion = models.TextField(blank=True)
    monto = models.PositiveIntegerField(help_text="Valor en COP")
    periodicidad = models.CharField(max_length=20, choices=PERIODICIDAD, default='mensual')
    fecha_vencimiento = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cuotas'
        ordering = ['-fecha_vencimiento']
        verbose_name = 'Cuota'
        verbose_name_plural = 'Cuotas'

    def __str__(self):
        return f"{self.nombre} — ${self.monto:,.0f}"

    @property
    def vencida(self):
        return timezone.now().date() > self.fecha_vencimiento


class Pago(models.Model):
    METODOS = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    ]

    cuota = models.ForeignKey(Cuota, on_delete=models.CASCADE, related_name='pagos')
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pagos'
    )
    monto_pagado = models.PositiveIntegerField(help_text="Valor en COP")
    metodo = models.CharField(max_length=20, choices=METODOS, default='transferencia')
    comprobante = models.CharField(max_length=100, blank=True,
                                   help_text="Número de comprobante o referencia")
    fecha_pago = models.DateField()
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pagos_registrados'
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pagos'
        ordering = ['-fecha_pago']
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        unique_together = [['cuota', 'propietario']]

    def __str__(self):
        return f"{self.propietario.nombre} — {self.cuota.nombre}"


class AuditLog(models.Model):
    ACCIONES = [
        ('visitante_creado', 'Visitante creado'),
        ('qr_validado', 'QR validado'),
        ('qr_invalido', 'QR inválido'),
        ('reserva_creada', 'Reserva creada'),
        ('reserva_fallida', 'Reserva fallida'),
        ('login', 'Inicio de sesión'),
        ('logout', 'Cierre de sesión'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    accion = models.CharField(max_length=50, choices=ACCIONES)
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-fecha']
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'
        indexes = [
            models.Index(fields=['fecha'], name='audit_fecha_idx'),
        ]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} — {self.get_accion_display()}"


class Novedad(models.Model):
    conjunto = models.ForeignKey('accounts.ConjuntoResidencial', on_delete=models.CASCADE, related_name='novedades')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='novedades')
    titulo = models.CharField(max_length=200)
    imagen = models.ImageField(upload_to='novedades/imagenes/', null=True, blank=True)
    contenido = models.TextField()
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'novedades'
        ordering = ['-created_at']
        verbose_name = 'Novedad'
        verbose_name_plural = 'Novedades'
        indexes = [
            models.Index(fields=['conjunto', 'activa', 'created_at'], name='novedad_conj_activa_idx'),
        ]

    def __str__(self):
        return self.titulo


class ArchivoNovedad(models.Model):
    novedad = models.ForeignKey(Novedad, on_delete=models.CASCADE, related_name='archivos')
    archivo = models.FileField(upload_to='novedades/archivos/')
    nombre_original = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'archivos_novedad'

    def __str__(self):
        return self.nombre_original

    def extension(self):
        name = self.nombre_original.lower()
        if name.endswith('.pdf'):   return 'pdf'
        if name.endswith(('.xls', '.xlsx')): return 'excel'
        if name.endswith('.txt'):   return 'txt'
        return 'archivo'


class ComentarioNovedad(models.Model):
    novedad = models.ForeignKey(Novedad, on_delete=models.CASCADE, related_name='comentarios')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texto = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comentarios_novedad'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.usuario.nombre} — {self.novedad.titulo}"


class LikeNovedad(models.Model):
    novedad = models.ForeignKey(Novedad, on_delete=models.CASCADE, related_name='likes')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes_novedad')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'likes_novedad'
        unique_together = [['novedad', 'usuario']]

    def __str__(self):
        return f"{self.usuario.nombre} ♥ {self.novedad.titulo}"


class NovedadVista(models.Model):
    novedad = models.ForeignKey(Novedad, on_delete=models.CASCADE, related_name='vistas')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='novedades_vistas')
    visto_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'novedades_vistas'
        unique_together = [['novedad', 'usuario']]
        indexes = [
            models.Index(fields=['usuario'], name='novedadvista_usuario_idx'),
        ]

    def __str__(self):
        return f"{self.usuario.nombre} vio {self.novedad.titulo}"


class Paquete(models.Model):
    EMPRESAS = [
        ('envia', 'Envia'),
        ('coordinadora', 'Coordinadora'),
        ('servientrega', 'Servientrega'),
        ('interrapidisimo', 'Interrapidísimo'),
        ('deprisa', 'Deprisa'),
        ('fedex', 'FedEx'),
        ('dhl', 'DHL'),
        ('amazon', 'Amazon Logistics'),
        ('mercadolibre', 'Mercado Libre'),
        ('tcc', 'TCC'),
        ('rappi', 'Rappi'),
        ('otro', 'Otro'),
    ]
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('entregado', 'Entregado'),
    ]

    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial', on_delete=models.CASCADE, related_name='paquetes'
    )
    torre = models.ForeignKey(
        'accounts.Torre', on_delete=models.SET_NULL, null=True, related_name='paquetes'
    )
    apartamento = models.CharField(max_length=10)
    empresa = models.CharField(max_length=30, choices=EMPRESAS)
    numero_guia = models.CharField(max_length=60, blank=True, help_text='Número de guía o tracking del operador')
    descripcion = models.CharField(max_length=200, blank=True, help_text='Ej: caja grande, sobre, etc.')
    codigo = models.CharField(max_length=6)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='pendiente')
    destinatario_nombre = models.CharField(max_length=100, blank=True)
    destinatario_telefono = models.CharField(max_length=20, blank=True)
    whatsapp_enviado = models.BooleanField(default=False)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='paquetes_registrados'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    entregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paquetes_entregados'
    )

    class Meta:
        ordering = ['-fecha_registro']
        verbose_name = 'Paquete'
        verbose_name_plural = 'Paquetes'

    def __str__(self):
        return f"Paquete {self.codigo} — Torre {self.torre} Apto {self.apartamento}"

    @property
    def empresa_display(self):
        return dict(self.EMPRESAS).get(self.empresa, self.empresa)


class ConfigParqueadero(models.Model):
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        related_name='config_parqueadero'
    )
    tipo_vehiculo = models.CharField(
        max_length=10,
        choices=[('carro', 'Carro'), ('moto', 'Moto')]
    )
    minutos_gracia = models.PositiveIntegerField(
        default=0,
        help_text='Minutos gratuitos antes de comenzar a cobrar'
    )
    valor_hora = models.DecimalField(
        max_digits=10, decimal_places=0, default=0,
        help_text='Valor por hora en COP después de la gracia'
    )
    fraccion_minutos = models.PositiveIntegerField(
        default=60,
        help_text='Fracción mínima de cobro en minutos (ej: 30 = cobrar por medias horas)'
    )

    class Meta:
        db_table = 'config_parqueadero'
        unique_together = [['conjunto', 'tipo_vehiculo']]

    def __str__(self):
        return f"{self.conjunto.nombre} - {self.get_tipo_vehiculo_display()}"


class LogEnvio(models.Model):
    """Registro de cada email o WhatsApp enviado por el sistema, por conjunto."""
    TIPO_CHOICES = [
        ('email',     'Email'),
        ('whatsapp',  'WhatsApp'),
    ]
    conjunto = models.ForeignKey(
        'accounts.ConjuntoResidencial',
        on_delete=models.CASCADE,
        related_name='log_envios',
        null=True, blank=True,
    )
    tipo     = models.CharField(max_length=10, choices=TIPO_CHOICES)
    fecha    = models.DateTimeField(auto_now_add=True, db_index=True)
    detalle  = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table  = 'log_envio'
        ordering  = ['-fecha']
        verbose_name        = 'Log de Envío'
        verbose_name_plural = 'Logs de Envíos'

    def __str__(self):
        conj = self.conjunto.nombre if self.conjunto_id else '—'
        return f"[{self.tipo}] {conj} — {self.fecha:%Y-%m-%d %H:%M}"


class ConfigGlobal(models.Model):
    """Configuración global del SaaS — singleton (siempre pk=1)."""
    limite_emails_mes     = models.PositiveIntegerField(default=1000, help_text='Límite mensual de emails (AWS SES)')
    limite_whatsapp_mes   = models.PositiveIntegerField(default=500,  help_text='Límite mensual de WhatsApp (Twilio)')

    class Meta:
        db_table  = 'config_global'
        verbose_name        = 'Configuración Global'
        verbose_name_plural = 'Configuración Global'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f'Config Global — emails: {self.limite_emails_mes} / WA: {self.limite_whatsapp_mes}'
