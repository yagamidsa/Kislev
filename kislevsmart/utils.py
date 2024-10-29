import logging
from django.shortcuts import redirect
from functools import wraps

logger = logging.getLogger(__name__)

def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Verificar si el usuario está autenticado
            if not request.user.is_authenticated:
                logger.warning(f"Intento de acceso no autenticado a {view_func.__name__}")
                return redirect('login')
            
            user_type = getattr(request.user, 'user_type', None)
            # Verificar si el tipo de usuario está permitido
            if user_type not in allowed_roles:
                logger.warning(f"Usuario {request.user.email} con rol {user_type} intentó acceder a {view_func.__name__}")
                return redirect('login')
            
            logger.info(f"Acceso autorizado: {request.user.email} ({user_type}) a {view_func.__name__}")
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator