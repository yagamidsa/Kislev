# accounts/backends.py
from django.contrib.auth.backends import BaseBackend
from django.db.models import Q
from .models import Usuario

class CedulaConjuntoBackend(BaseBackend):
    def authenticate(self, request, cedula=None, conjunto=None, password=None):
        try:
            # Generar unique_cedula
            unique_cedula = f"{cedula}_{conjunto.id}"
            
            user = Usuario.objects.get(
                unique_cedula=unique_cedula,
                is_active=True
            )
            
            if user.check_password(password):
                return user
            return None
        except Usuario.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None