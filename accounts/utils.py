from django.shortcuts import redirect
from functools import wraps

def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Verificar si el usuario está autenticado
            if not request.user.is_authenticated:
                return redirect('login')

            # Verificar si el tipo de usuario está permitido
            if getattr(request.user, 'user_type', None) not in allowed_roles:
                return redirect('login')

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator