import logging
import re
import threading
import requests as _requests
from django.conf import settings as _settings

from accounts.utils import role_required  # noqa: F401

logger = logging.getLogger(__name__)


def send_email_async(msg, detalle: str = 'email') -> None:
    """
    Envía un EmailMessage / EmailMultiAlternatives en un hilo daemon.
    El request retorna inmediatamente; el envío ocurre en background.
    Los errores se registran en el log pero nunca bloquean la respuesta.

    Uso:
        from kislevsmart.utils import send_email_async
        send_email_async(email_message)

    No usar para el envío masivo (send_service_notification) que ya
    gestiona su propio bucle y necesita contabilizar éxitos/fallos.
    """
    def _send():
        try:
            msg.send(fail_silently=False)
            logger.info(f"[email_async] Enviado OK — {detalle}")
        except Exception as exc:
            logger.error(f"[email_async] Error enviando {detalle}: {exc}")

    t = threading.Thread(target=_send, daemon=True)
    t.start()


def _normalizar_telefono(phone):
    """Convierte número colombiano a formato internacional 57XXXXXXXXXX."""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('57') and len(digits) == 12:
        return digits
    if digits.startswith('3') and len(digits) == 10:
        return '57' + digits
    return digits  # devuelve lo que tenga, Meta lo rechazará si es inválido


def send_whatsapp(phone: str, message: str, conjunto=None, detalle: str = 'WhatsApp') -> bool:
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
            log_envio('whatsapp', conjunto=conjunto, detalle=detalle)
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


def log_envio(tipo: str, conjunto=None, detalle: str = '') -> None:
    """Registra un email o WhatsApp enviado en LogEnvio. Falla silenciosamente."""
    try:
        from kislevsmart.models import LogEnvio
        LogEnvio.objects.create(tipo=tipo, conjunto=conjunto, detalle=detalle[:200])
    except Exception:
        pass


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