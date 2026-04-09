import logging
import re
import requests as _requests
from django.conf import settings as _settings

from accounts.utils import role_required  # noqa: F401

logger = logging.getLogger(__name__)


def _normalizar_telefono(phone):
    """Convierte número colombiano a formato internacional 57XXXXXXXXXX."""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('57') and len(digits) == 12:
        return digits
    if digits.startswith('3') and len(digits) == 10:
        return '57' + digits
    return digits  # devuelve lo que tenga, Meta lo rechazará si es inválido


def send_whatsapp(phone: str, message: str) -> bool:
    """
    Envía un mensaje de WhatsApp usando Twilio.
    Retorna True si se envió, False en caso de error.
    Requiere TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM en settings/env.
    """
    account_sid = getattr(_settings, 'TWILIO_ACCOUNT_SID', '')
    auth_token = getattr(_settings, 'TWILIO_AUTH_TOKEN', '')
    from_number = getattr(_settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')

    if not account_sid or not auth_token:
        logger.warning('WhatsApp no configurado: TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN faltantes')
        return False

    to = 'whatsapp:+' + _normalizar_telefono(phone)
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    try:
        resp = _requests.post(
            url,
            data={'From': from_number, 'To': to, 'Body': message},
            auth=(account_sid, auth_token),
            timeout=10,
        )
        if resp.status_code == 201:
            return True
        logger.error('Twilio API error %s: %s', resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        logger.error('Twilio send exception: %s', exc)
        return False


def mensaje_paquete(nombre, conjunto, torre, apartamento, empresa, fecha, hora, codigo):
    """Construye el mensaje de WhatsApp para notificación de paquete."""
    return (
        f"📦 *¡Llegó un paquete para ti!*\n\n"
        f"Hola, {nombre}! 👋\n\n"
        f"Tienes un paquete esperándote en la portería de *{conjunto}*.\n\n"
        f"📍 *Torre:* {torre}\n"
        f"🏠 *Apto:* {apartamento}\n"
        f"🚚 *Empresa:* {empresa}\n"
        f"📅 *Fecha:* {fecha}\n"
        f"⏰ *Hora:* {hora}\n\n"
        f"Tu código de retiro es:\n\n"
        f"🔐  *{codigo}*  🔐\n\n"
        f"Preséntalo en portería al momento de recoger tu pedido.\n\n"
        f"_Este mensaje es automático · {conjunto}_"
    )


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


def calcular_cobro_parqueadero(entrada_dt, config):
    """
    Calcula el tiempo y valor a cobrar por permanencia en parqueadero.
    Returns: (valor_cop: int, minutos_total: int, en_gracia: bool)
    """
    import math
    from django.utils import timezone
    now = timezone.localtime(timezone.now())
    entrada = timezone.localtime(entrada_dt)
    minutos_total = int((now - entrada).total_seconds() / 60)

    if not config or int(config.valor_hora) == 0:
        return 0, minutos_total, True

    minutos_cobrar = max(0, minutos_total - config.minutos_gracia)
    if minutos_cobrar == 0:
        return 0, minutos_total, True

    fraccion = config.fraccion_minutos or 60
    fracciones = math.ceil(minutos_cobrar / fraccion)
    valor_fraccion = float(config.valor_hora) * fraccion / 60
    valor = int(fracciones * valor_fraccion)
    return valor, minutos_total, False