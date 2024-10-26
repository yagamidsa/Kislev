from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

class UsuarioManager(BaseUserManager):
    def create_user(self, usuario, password=None, **extra_fields):
        if not usuario:
            raise ValueError('El usuario debe tener un nombre de usuario')
        usuario = self.model(usuario=usuario, **extra_fields)
        usuario.set_password(password)  # Guarda la contraseña de forma segura
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, usuario, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(usuario, password, **extra_fields)

    def get_by_natural_key(self, usuario):
        return self.get(usuario=usuario)
    
class Usuario(AbstractBaseUser):
    USER_TYPES = (
        ('propietario', 'Propietario'),
        ('administrador', 'Administrador'),
        ('porteria', 'Portería'),
    )

    # Nuevos campos
    nombre = models.CharField(max_length=100)  # Campo para el nombre
    email = models.EmailField(unique=True)  # Campo para el email
    usuario = models.PositiveIntegerField(unique=True)  # Campo para usuario, solo numérico
    password = models.CharField(max_length=128)  # Campo para la contraseña
    phone_number = models.CharField(max_length=15, blank=True, null=True)  # Campo para el número de teléfono
    user_type = models.CharField(max_length=15, choices=USER_TYPES, default='propietario')  # Tipo de usuario
    is_active = models.BooleanField(default=True)  # Si el usuario está activo
    is_staff = models.BooleanField(default=False)  # Si el usuario es parte del staff
    last_login = models.DateTimeField(blank=True, null=True)  # Último inicio de sesión

    objects = UsuarioManager()

    USERNAME_FIELD = 'usuario'
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.usuario} {self.email} ({self.user_type})"