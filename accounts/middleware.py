# accounts/middleware.py
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import login
from django.utils import timezone

_COOKIE_NAME = 'kislev_token'

# ── Auto-login por token persistente ────────────────────────────────────────

class PersistentLoginMiddleware:
    """
    Si el usuario no tiene sesión activa pero trae la cookie kislev_token,
    valida el token en DB y lo loguea automáticamente sin pedir credenciales.
    El token dura 30 días o hasta que el usuario cierre sesión explícitamente.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            token_value = request.COOKIES.get(_COOKIE_NAME)
            if token_value:
                self._try_auto_login(request, token_value)

        response = self.get_response(request)

        # Si el token era inválido/expirado, eliminarlo del navegador
        if getattr(request, '_clear_kislev_token', False):
            response.delete_cookie(_COOKIE_NAME, path='/', samesite='Lax')

        return response

    def _try_auto_login(self, request, token_value):
        from .models import PersistentLoginToken
        try:
            record = PersistentLoginToken.objects.select_related('user').get(
                token=token_value,
                expires_at__gt=timezone.now(),
            )
            user = record.user
            if user.is_active:
                user.backend = 'accounts.backends.CedulaConjuntoBackend'
                login(request, user)
        except PersistentLoginToken.DoesNotExist:
            request._clear_kislev_token = True


# ── URLs que no deben redirigir ──────────────────────────────────────────────

# URLs that must always be accessible (no redirect loop)
_EXEMPT_PREFIXES = (
    '/accounts/login/',
    '/accounts/logout/',
    '/accounts/force-password-change/',
    '/accounts/cambiar-password/',
    '/accounts/recuperar-password/',
    '/accounts/password_reset/',
    '/accounts/reset/',
    '/static/',
    '/media/',
    '/admin/',
)


class ForcePasswordChangeMiddleware:
    """
    If a logged-in user has must_change_password=True, redirect every
    request to the force-password-change page until they comply.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'must_change_password', False)
            and not any(request.path.startswith(p) for p in _EXEMPT_PREFIXES)
        ):
            return redirect(reverse('accounts:force_password_change'))

        return self.get_response(request)
