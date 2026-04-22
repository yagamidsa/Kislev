# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

class ConjuntoResidencial(models.Model):
    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=255)
    nit = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=15, blank=True, null=True)
    email_contacto = models.EmailField(blank=True, null=True)
    estado = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    link_pago = models.URLField(max_length=500, blank=True, null=True, help_text='Link del portal de pagos para este conjunto')
    nombre_agrupacion = models.CharField(
        max_length=50,
        default='Torre',
        blank=True,
        help_text='Nombre del nivel de agrupación (ej: Torre, Bloque, Interior). Dejar vacío si no hay agrupación.',
    )
    nombre_unidad = models.CharField(
        max_length=50,
        default='Apto',
        help_text='Nombre de la unidad mínima (ej: Apto, Casa, PH).',
    )
    horario_atencion = models.TextField(
        blank=True,
        default='',
        help_text='Horario de atención de la administración (texto libre, ej: Lunes a viernes 8–17 h).',
    )
    cuota_almacenamiento_mb = models.PositiveIntegerField(
        default=2048,
        help_text='Espacio máximo en MB que puede usar este conjunto para archivos e imágenes (default 2 GB).',
    )

    @property
    def etiqueta_agrupacion(self):
        """Nombre de la agrupación principal o vacío si no aplica."""
        return self.nombre_agrupacion or ''

    @property
    def etiqueta_unidad(self):
        """Nombre de la unidad mínima."""
        return self.nombre_unidad or 'Apto'

    @property
    def tiene_agrupacion(self):
        """True si el conjunto usa agrupaciones (torres, bloques, etc.)."""
        return bool(self.nombre_agrupacion)

    class Meta:
        verbose_name = 'Conjunto Residencial'
        verbose_name_plural = 'Conjuntos Residenciales'
        db_table = 'conjunto_residencial'

    def __str__(self):
        return self.nombre



class Torre(models.Model):
    """Modelo para representar las torres o interiores de un conjunto"""
    conjunto = models.ForeignKey(ConjuntoResidencial, on_delete=models.CASCADE, related_name='torres')
    nombre = models.CharField(max_length=100, help_text="Nombre de la torre o interior (ej: Torre 1, Interior A)")
    numero_pisos = models.PositiveIntegerField(default=1, help_text="Número de pisos en esta torre")
    aptos_por_piso = models.PositiveIntegerField(default=4, help_text="Número de apartamentos por piso")
    activo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Torre/Interior'
        verbose_name_plural = 'Torres/Interiores'
        unique_together = [['conjunto', 'nombre']]
        
    def __str__(self):
        return f"{self.nombre} - {self.conjunto.nombre}"
    
    def get_apartamentos(self):
        """Genera la lista de todos los apartamentos en esta torre"""
        apartamentos = []
        for piso in range(1, self.numero_pisos + 1):
            for apto in range(1, self.aptos_por_piso + 1):
                num_apto = f"{piso:02d}{apto:02d}"  # Por ejemplo: 0101, 0102, 0201, 0202
                apartamentos.append(num_apto)
        return apartamentos


class UsuarioManager(BaseUserManager):
    def create_user(self, cedula, nombre, email, password=None, **extra_fields):
        if not cedula:
            raise ValueError('El usuario debe tener una cédula')
        if not nombre:
            raise ValueError('El usuario debe tener un nombre')
        if not email:
            raise ValueError('El usuario debe tener un email')

        # Asegurar que existe el conjunto por defecto
        conjunto = extra_fields.get('conjunto')
        if not conjunto:
            conjunto = ConjuntoResidencial.objects.first()
            if not conjunto:
                raise ValueError("Crea al menos un ConjuntoResidencial antes de crear usuarios.")
            extra_fields['conjunto'] = conjunto

        # Generar unique_cedula
        unique_cedula = f"{cedula}_{conjunto.id}"
        
        usuario = self.model(
            cedula=cedula,
            unique_cedula=unique_cedula,
            nombre=nombre,
            email=self.normalize_email(email),
            **extra_fields
        )
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, cedula, nombre, email, password=None):
        conjunto = ConjuntoResidencial.objects.first()
        if not conjunto:
            raise ValueError("Crea al menos un ConjuntoResidencial antes de crear un superusuario.")
        
        return self.create_user(
            cedula=cedula,
            nombre=nombre,
            email=email,
            password=password,
            conjunto=conjunto,
            is_staff=True,
            is_superuser=True,
            user_type='administrador'
        )

class Usuario(AbstractBaseUser):
    cedula = models.CharField(max_length=20)
    unique_cedula = models.CharField(max_length=50, unique=True, editable=False)
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    conjunto = models.ForeignKey(ConjuntoResidencial, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    user_type = models.CharField(
        max_length=15,
        choices=[
            ('propietario', 'Propietario'),
            ('administrador', 'Administrador'),
            ('porteria', 'Portería'),
        ],
        default='propietario'
    )
    # Relación con torre (en lugar de un campo fijo)
    torre = models.ForeignKey(
    'Torre',  # Usando el nombre como string evita problemas de importación circular
    on_delete=models.SET_NULL, 
    null=True, 
    blank=True,
    related_name='residentes'
    )
    # Campo para el número de apartamento
    apartamento = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text="Número de apartamento"
    )
    es_arrendatario = models.BooleanField(
        default=False,
        help_text='Si es True, el usuario es arrendatario (user_type=propietario pero no dueño del inmueble)'
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_saas_owner = models.BooleanField(default=False, help_text='Propietario del SaaS — accede a todos los conjuntos')
    must_change_password = models.BooleanField(default=False, help_text='Fuerza cambio de contraseña en el próximo login')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'cedula'
    REQUIRED_FIELDS = ['nombre', 'email']

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        unique_together = [['cedula', 'conjunto']]
        db_table = 'usuarios'

    def save(self, *args, **kwargs):
        if not self.unique_cedula and self.conjunto_id:
            self.unique_cedula = f"{self.cedula}_{self.conjunto_id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - CC: {self.cedula} ({self.conjunto.nombre})"

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def get_ubicacion_completa(self):
        """Ubicación completa usando las etiquetas del tipo de distribución del conjunto."""
        if self.user_type not in ('propietario',):
            return "Sin ubicación asignada"

        conjunto = self.conjunto
        tiene_agrupacion = conjunto.tiene_agrupacion
        etiqueta_unidad = conjunto.etiqueta_unidad
        etiqueta_agrup = conjunto.etiqueta_agrupacion

        if tiene_agrupacion:
            if self.torre and self.apartamento:
                return f"{etiqueta_agrup} {self.torre.nombre} — {etiqueta_unidad} {self.apartamento}"
            elif self.torre:
                return f"{etiqueta_agrup} {self.torre.nombre}"
            elif self.apartamento:
                return f"{etiqueta_unidad} {self.apartamento}"
        else:
            if self.apartamento:
                return f"{etiqueta_unidad} {self.apartamento}"

        return "Sin ubicación asignada"