# accounts/middleware.py
from django.shortcuts import redirect
from django.urls import reverse


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
