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

    class Meta:
        verbose_name = 'Conjunto Residencial'
        verbose_name_plural = 'Conjuntos Residenciales'
        db_table = 'conjunto_residencial'

    def __str__(self):
        return self.nombre

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
            try:
                conjunto = ConjuntoResidencial.objects.get(nombre="Oliva-Amarilo")
            except ConjuntoResidencial.DoesNotExist:
                raise ValueError("No existe el Conjunto Principal")
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
        try:
            conjunto = ConjuntoResidencial.objects.get(nombre="Oliva-Amarilo")
        except ConjuntoResidencial.DoesNotExist:
            raise ValueError("El Conjunto Principal debe existir antes de crear un superusuario")
        
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
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
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