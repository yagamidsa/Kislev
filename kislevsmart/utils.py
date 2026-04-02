from accounts.utils import role_required  # noqa: F401


def log_audit(request, accion, detalle=''):
    """Registra una acción crítica en el AuditLog."""
    from kislevsmart.models import AuditLog
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
        or request.META.get('REMOTE_ADDR')
    usuario = request.user if request.user.is_authenticated else None
    conjunto = getattr(usuario, 'conjunto', None) if usuario else None
    try:
        AuditLog.objects.create(
            usuario=usuario,
            conjunto=conjunto,
            accion=accion,
            detalle=detalle,
            ip=ip or None,
        )
    except Exception:
        pass