from django.contrib.auth.backends import BaseBackend
from django.db.models import Q
from .models import Usuario

class CedulaConjuntoBackend(BaseBackend):
    def authenticate(self, request, cedula=None, conjunto=None, password=None):
        try:
            # Si se proporciona un conjunto, usamos el método original
            if conjunto:
                # Generar unique_cedula
                unique_cedula = f"{cedula}_{conjunto.id}"
                
                # Usamos filter().first() en lugar de get() para evitar MultipleObjectsReturned
                user = Usuario.objects.filter(
                    cedula=cedula,
                    conjunto=conjunto,
                    is_active=True
                ).first()
                
                if user and user.check_password(password):
                    return user
                return None
            else:
                # Si no se proporciona conjunto, verificamos si la cédula existe en algún conjunto
                # y si la contraseña es válida
                usuarios = Usuario.objects.filter(
                    cedula=cedula,
                    is_active=True
                )
                
                # Si no hay usuarios con esa cédula
                if not usuarios.exists():
                    return None
                
                # Verificamos si alguno de los usuarios tiene la contraseña correcta
                for user in usuarios:
                    if user.check_password(password):
                        return user
                
                return None
        except Exception as e:
            # Log error if needed
            print(f"Error en autenticación: {e}")
            return None

    def get_user(self, user_id):
        try:
            return Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None