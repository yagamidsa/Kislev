import base64
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.views.decorators.csrf import csrf_protect
import qrcode
import uuid, os
from io import BytesIO
from cryptography.fernet import Fernet
from datetime import datetime, time, timedelta
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from cryptography.fernet import InvalidToken
from django.core.mail import EmailMessage
from .models import Visitante
from .utils import role_required, log_audit
from django.db.models import Count, F
from django.db.models.functions import ExtractMonth, ExtractWeekDay, ExtractHour
import json
from accounts.models import Usuario, ConjuntoResidencial, Torre
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.views.generic import ListView
from .models import Sala, Reserva, BloqueoSala, Paquete
import logging
from django.contrib import messages
from django.db import DatabaseError, transaction, models
from django.http import HttpResponse
from django.views.decorators.vary import vary_on_headers
from .models import VisitanteVehicular
from .models import ParqueaderoCarro, ParqueaderoMoto, Cuota, Pago, Novedad, ArchivoNovedad, ComentarioNovedad, LikeNovedad, NovedadVista
from django.core.mail import EmailMultiAlternatives



def sanitize_text(text):
    """
    Limpia el texto de caracteres inválidos para UTF-8 de forma agresiva
    """
    if not text:
        return ""
    
    try:
        text = str(text)
        # Remover surrogates de forma agresiva
        # Codificar a UTF-8 ignorando errores, luego decodificar
        clean_text = text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='ignore')
        return clean_text
    except Exception as e:
        logger.error(f"Error en sanitize_text: {e}")
        # Fallback: solo dejar caracteres ASCII seguros
        return ''.join(c for c in str(text) if ord(c) < 128)

# Configurar logger
logger = logging.getLogger(__name__)


#salas
class SalaListView(ListView):
    model = Sala
    template_name = 'salas/lista_salas.html'
    context_object_name = 'salas'

    def get_queryset(self):
        hoy = timezone.now().date()
        salas = Sala.objects.filter(estado=True, conjunto=self.request.user.conjunto)
        # Annotate each sala with its active BloqueoSala (if any)
        for sala in salas:
            sala.bloqueo_activo = BloqueoSala.objects.filter(
                sala=sala, fecha_inicio__lte=hoy, fecha_fin__gte=hoy
            ).first()
        return salas

def get_reservas_sala(request, sala_id):
    """
    API endpoint para obtener las reservas de una sala en formato JSON
    """
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)
    
    sala = get_object_or_404(Sala, id=sala_id)
    reservas = Reserva.objects.filter(
        sala=sala,
        fecha__range=[start_date, end_date]
    )
    
    eventos = []
    for reserva in reservas:
        eventos.append({
            'id': reserva.id,
            'title': 'Reservado',
            'start': f"{reserva.fecha}T{reserva.hora_inicio}",
            'end': f"{reserva.fecha}T{reserva.hora_fin}",
            'color': '#FF3B30'  # Color rojo de Apple
        })
    
    # Agregar días disponibles en verde
    current = start
    while current <= end:
        if not any(r.fecha == current.date() for r in reservas):
            eventos.append({
                'start': current.strftime('%Y-%m-%d'),
                'end': current.strftime('%Y-%m-%d'),
                'rendering': 'background',
                'color': '#34C759'  # Color verde de Apple
            })
        current += timedelta(days=1)
    
    return JsonResponse(eventos, safe=False)

def calendario_sala(request, sala_id):
    """
    Vista para mostrar el calendario de una sala específica
    """
    sala = get_object_or_404(Sala, id=sala_id)
    
    # Obtener el mes actual para el calendario
    today = datetime.now()
    start_date = today.replace(day=1)
    
    # Verificar si hay una fecha específica en los parámetros
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today.date()
    else:
        selected_date = today.date()

    # Obtener las reservas del mes actual
    reservas_mes = Reserva.objects.filter(
        sala=sala,
        fecha__year=selected_date.year,
        fecha__month=selected_date.month
    )

    # Preparar datos para el calendario
    dias_ocupados = {
        reserva.fecha.strftime('%Y-%m-%d'): {
            'estado': 'ocupado',
            'hora_inicio': reserva.hora_inicio.strftime('%H:%M'),
            'hora_fin': reserva.hora_fin.strftime('%H:%M')
        }
        for reserva in reservas_mes
    }

    context = {
        'sala': sala,
        'dias_ocupados': json.dumps(dias_ocupados),
        'fecha_seleccionada': selected_date.strftime('%Y-%m-%d'),
        'hora_actual': today.strftime('%H:%M'),
    }
    
    return render(request, 'salas/calendario.html', context)

def get_horarios_disponibles(request, sala_id, fecha):
    sala = get_object_or_404(Sala, id=sala_id)
    try:
        fecha_consulta = datetime.strptime(fecha, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)

    # Sala bloqueada por mantenimiento ese día → sin slots
    if BloqueoSala.objects.filter(sala=sala, fecha_inicio__lte=fecha_consulta, fecha_fin__gte=fecha_consulta).exists():
        return JsonResponse({'fecha': fecha, 'slots_disponibles': [], 'bloqueada': True})

    HORARIOS_OPERACION = [
        ('08:00', '09:00'), ('09:00', '10:00'), ('10:00', '11:00'),
        ('11:00', '12:00'), ('12:00', '13:00'), ('13:00', '14:00'),
        ('14:00', '15:00'), ('15:00', '16:00'), ('16:00', '17:00'),
        ('17:00', '18:00'), ('18:00', '19:00'), ('19:00', '20:00'),
        ('20:00', '21:00'), ('21:00', '22:00'),
    ]

    reservas_dia = Reserva.objects.filter(sala=sala, fecha=fecha_consulta).order_by('hora_inicio')
    slots_ocupados = [(r.hora_inicio.strftime('%H:%M'), r.hora_fin.strftime('%H:%M')) for r in reservas_dia]

    slots_disponibles = []
    for inicio, fin in HORARIOS_OPERACION:
        libre = all(fin <= oi or inicio >= of for oi, of in slots_ocupados)
        if libre:
            slots_disponibles.append({'inicio': inicio, 'fin': fin})

    if fecha_consulta < datetime.now().date():
        slots_disponibles = []
    elif fecha_consulta == datetime.now().date():
        hora_actual = datetime.now().time()
        slots_disponibles = [s for s in slots_disponibles if datetime.strptime(s['inicio'], '%H:%M').time() > hora_actual]

    return JsonResponse({'fecha': fecha, 'slots_disponibles': slots_disponibles})

@login_required
def reservar_sala(request, sala_id):
    sala = get_object_or_404(Sala, id=sala_id)

    # Build bloqueos JSON for the calendar (next 6 months)
    hoy = timezone.now().date()
    from datetime import date as date_type
    limite = date_type(hoy.year + 1, hoy.month, 1)
    bloqueos_qs = BloqueoSala.objects.filter(sala=sala, fecha_fin__gte=hoy)
    bloqueos_json = json.dumps([
        {'inicio': str(b.fecha_inicio), 'fin': str(b.fecha_fin), 'motivo': b.motivo}
        for b in bloqueos_qs
    ])

    if request.method == 'POST':
        fecha = request.POST.get('fecha')
        hora_inicio = request.POST.get('hora_inicio')
        hora_fin = request.POST.get('hora_fin')
        notas = request.POST.get('notas', '')
        torre_id = request.POST.get('torre_id', '')
        apartamento_post = request.POST.get('apartamento', '')

        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            hora_inicio_obj = datetime.strptime(hora_inicio, '%H:%M').time()
            hora_fin_obj = datetime.strptime(hora_fin, '%H:%M').time()

            if fecha_obj < datetime.now().date():
                raise ValueError('No se pueden hacer reservas en fechas pasadas')
            if hora_inicio_obj < datetime.strptime('08:00', '%H:%M').time() or \
               hora_fin_obj > datetime.strptime('22:00', '%H:%M').time():
                raise ValueError('El horario debe estar entre 8:00 AM y 10:00 PM')
            if hora_fin_obj <= hora_inicio_obj:
                raise ValueError('La hora de finalización debe ser posterior a la de inicio')

            if BloqueoSala.objects.filter(sala=sala, fecha_inicio__lte=fecha_obj, fecha_fin__gte=fecha_obj).exists():
                raise ValueError('La sala está en mantenimiento en esa fecha')

            # Determinar usuario de la reserva
            es_admin = request.user.user_type == 'administrador'
            usuario_reserva = request.user
            if es_admin and torre_id and apartamento_post:
                from accounts.models import Torre as TorreModel
                torre_obj = TorreModel.objects.filter(id=torre_id, conjunto=request.user.conjunto).first()
                if torre_obj:
                    residente = Usuario.objects.filter(
                        conjunto=request.user.conjunto, torre=torre_obj,
                        apartamento=apartamento_post, user_type='propietario'
                    ).first()
                    if residente:
                        usuario_reserva = residente

            with transaction.atomic():
                existe = Reserva.objects.select_for_update().filter(
                    sala=sala, fecha=fecha_obj,
                    hora_inicio__lt=hora_fin_obj, hora_fin__gt=hora_inicio_obj,
                    estado__in=['pendiente', 'aprobada'],
                ).exists()
                if existe:
                    raise ValueError('Ya existe una reserva para ese horario')
                Reserva.objects.create(
                    sala=sala, fecha=fecha_obj,
                    hora_inicio=hora_inicio_obj, hora_fin=hora_fin_obj,
                    notas=notas, usuario=usuario_reserva,
                    estado='aprobada' if es_admin else 'pendiente',
                    aprobada_por=request.user if es_admin else None,
                )
                log_audit(request, 'reserva_creada',
                          f"Sala: {sala.nombre} | Fecha: {fecha_obj} | {hora_inicio_obj}-{hora_fin_obj}")

            if es_admin:
                messages.success(request, f'Reserva confirmada — {sala.nombre} · {fecha_obj.strftime("%d/%m/%Y")} {hora_inicio}-{hora_fin}')
            else:
                messages.success(request, f'Reserva enviada — {sala.nombre} · {fecha_obj.strftime("%d/%m/%Y")} {hora_inicio}-{hora_fin} · Pendiente de aprobación del administrador')
            return redirect('mis_reservas')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            import traceback
            messages.error(request, f'Error: {e} | {traceback.format_exc()[-300:]}')

    from accounts.models import Torre as TorreModel
    from django.db.models.functions import Length
    torres = TorreModel.objects.filter(conjunto=request.user.conjunto, activo=True).order_by(Length('nombre'), 'nombre') if request.user.user_type == 'administrador' else []
    return render(request, 'salas/reservar.html', {'sala': sala, 'bloqueos_json': bloqueos_json, 'torres': torres})

@login_required
def mis_reservas(request):
    user = request.user
    if user.user_type == 'administrador':
        reservas = Reserva.objects.filter(
            sala__conjunto=user.conjunto
        ).select_related('sala', 'usuario').order_by('-created_at')
    else:
        reservas = Reserva.objects.filter(
            usuario=user
        ).select_related('sala').order_by('-created_at')
    return render(request, 'salas/mis_reservas.html', {'reservas': reservas})


@login_required
def cancelar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.user.user_type != 'administrador' and reserva.usuario != request.user:
        messages.error(request, 'No tienes permiso para cancelar esta reserva')
        return redirect('mis_reservas')
    if reserva.estado not in ('pendiente', 'aprobada'):
        messages.error(request, 'Esta reserva no se puede cancelar')
        return redirect('mis_reservas')
    if request.method == 'POST':
        from django.utils import timezone as _tz
        reserva.estado = 'cancelada'
        reserva.aprobada_por = request.user
        reserva.fecha_aprobacion = _tz.now()
        reserva.motivo_rechazo = f'Cancelada por {request.user.nombre}'
        reserva.save(update_fields=['estado', 'aprobada_por', 'fecha_aprobacion', 'motivo_rechazo'])
        messages.success(request, 'Reserva cancelada')
        return redirect('mis_reservas')
    return render(request, 'salas/confirmar_cancelacion.html', {'reserva': reserva})


@login_required
@role_required(['administrador'])
def aprobar_reserva(request, reserva_id):
    from django.utils import timezone as _tz
    if request.method != 'POST':
        return redirect('mis_reservas')
    reserva = get_object_or_404(Reserva, id=reserva_id, sala__conjunto=request.user.conjunto)
    accion = request.POST.get('accion')
    if accion == 'aprobar':
        reserva.estado = 'aprobada'
        reserva.aprobada_por = request.user
        reserva.fecha_aprobacion = _tz.now()
        reserva.motivo_rechazo = ''
        reserva.save(update_fields=['estado', 'aprobada_por', 'fecha_aprobacion', 'motivo_rechazo'])
        messages.success(request, f'Reserva de {reserva.sala.nombre} aprobada')
    elif accion == 'rechazar':
        motivo = request.POST.get('motivo', '').strip()
        reserva.estado = 'rechazada'
        reserva.aprobada_por = request.user
        reserva.fecha_aprobacion = _tz.now()
        reserva.motivo_rechazo = motivo
        reserva.save(update_fields=['estado', 'aprobada_por', 'fecha_aprobacion', 'motivo_rechazo'])
        messages.success(request, f'Reserva de {reserva.sala.nombre} rechazada')
    next_url = request.POST.get('next', 'mis_reservas')
    return redirect(next_url)


@login_required
def bloquear_sala(request):
    if request.user.user_type != 'administrador':
        messages.error(request, 'Acceso restringido')
        return redirect('lista_salas')

    salas = Sala.objects.filter(estado=True, conjunto=request.user.conjunto)
    hoy = timezone.now().date()
    bloqueos = BloqueoSala.objects.filter(
        sala__conjunto=request.user.conjunto, fecha_fin__gte=hoy
    ).select_related('sala').order_by('fecha_inicio')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            bloqueo_id = request.POST.get('bloqueo_id')
            bloqueo = get_object_or_404(BloqueoSala, id=bloqueo_id, sala__conjunto=request.user.conjunto)
            bloqueo.delete()
            messages.success(request, 'Bloqueo eliminado correctamente')
            return redirect('bloquear_sala')

        sala_id = request.POST.get('sala')
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        motivo = request.POST.get('motivo', 'Mantenimiento').strip() or 'Mantenimiento'

        try:
            sala = get_object_or_404(Sala, id=sala_id, conjunto=request.user.conjunto)
            fi = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            ff = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            if ff < fi:
                raise ValueError('La fecha fin debe ser igual o posterior a la fecha inicio')
            BloqueoSala.objects.create(sala=sala, fecha_inicio=fi, fecha_fin=ff, motivo=motivo, creado_por=request.user)
            messages.success(request, f'{sala.nombre} bloqueada del {fi.strftime("%d/%m/%Y")} al {ff.strftime("%d/%m/%Y")}')
            return redirect('bloquear_sala')
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, 'salas/bloquear_sala.html', {
        'salas': salas,
        'bloqueos': bloqueos,
        'hoy': hoy.strftime('%Y-%m-%d'),
    })









# S.Generales
logger = logging.getLogger(__name__)

@require_http_methods(["POST"])
def procesar_envio(request):
    try:
        # 1. Validar mensaje
        mensaje_usuario = request.POST.get('message')
        if not mensaje_usuario:
            return JsonResponse({
                'status': 'error',
                'message': 'El mensaje es requerido'
            })

        # 2. Sanitizar y preparar mensaje (conservar formato HTML)
        mensaje_usuario = sanitize_text(mensaje_usuario)
        mensaje_usuario = mensaje_usuario.replace('\n', '<br>')

        # 3. Obtener propietarios DEL CONJUNTO ACTUAL
        conjunto_actual = request.user.conjunto
        
        # Filtrar propietarios solo del conjunto actual
        propietarios = Usuario.objects.filter(
            user_type='propietario',
            is_active=True,
            conjunto=conjunto_actual
        ).values('email', 'nombre')

        total_propietarios = propietarios.count()

        logger.info(f"Seleccionando propietarios del conjunto: {conjunto_actual.nombre} (ID: {conjunto_actual.id})")
        logger.info(f"Total de propietarios encontrados en este conjunto: {total_propietarios}")

        if not total_propietarios:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay propietarios activos en este conjunto'
            })
        
        # 4. Procesar archivos adjuntos si existen
        attachments_data = []
        files = request.FILES.getlist('fileInput')
        total_size = 0
        MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024
        MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024
        MAX_FILES = 10
        
        if len(files) > MAX_FILES:
            logger.warning(f"Intento de enviar demasiados archivos: {len(files)}")
            return JsonResponse({
                'status': 'error',
                'message': f'No se pueden adjuntar más de {MAX_FILES} archivos'
            })
        
        for archivo in files:
            try:
                if archivo.size > MAX_SINGLE_FILE_SIZE:
                    logger.warning(f"Archivo demasiado grande: {archivo.name} ({archivo.size/(1024*1024):.2f}MB)")
                    return JsonResponse({
                        'status': 'error',
                        'message': f'El archivo {archivo.name} supera el límite de 10MB'
                    })
                
                total_size += archivo.size
                if total_size > MAX_ATTACHMENT_SIZE:
                    logger.warning(f"Tamaño total de archivos excedido: {total_size/(1024*1024):.2f}MB")
                    return JsonResponse({
                        'status': 'error',
                        'message': f'El tamaño total de los archivos supera el límite de 25MB'
                    })
                
                archivo_contenido = archivo.read()
                archivo_nombre_limpio = sanitize_text(archivo.name)
                
                # Guardar info del archivo para adjuntar después
                attachments_data.append({
                    'filename': archivo_nombre_limpio,
                    'content': archivo_contenido,
                    'content_type': archivo.content_type
                })
                
                logger.info(f"Archivo adjunto procesado: {archivo_nombre_limpio} ({archivo.size/(1024*1024):.2f}MB)")
            except Exception as e:
                logger.error(f"Error procesando archivo {archivo.name}: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error procesando el archivo {archivo.name}: {str(e)}'
                })

        # 5. Preparar envío por lotes
        from django.core.mail import EmailMultiAlternatives
        
        BATCH_SIZE = 500
        total_enviados = 0
        propietarios_list = list(propietarios)
        
        total_lotes = (len(propietarios_list) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(f"Iniciando envío a {total_propietarios} propietarios en {total_lotes} lotes con {len(attachments_data)} archivos adjuntos")
        
        # 6. Procesar cada lote
        for i in range(0, len(propietarios_list), BATCH_SIZE):
            batch = propietarios_list[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            first_prop = batch[0]
            other_props = batch[1:]
            
            # SANITIZAR TODOS LOS DATOS DEL PROPIETARIO
            nombre_limpio = sanitize_text(first_prop['nombre'])
            email_limpio = sanitize_text(first_prop['email'])
            conjunto_nombre_limpio = sanitize_text(getattr(request.user.conjunto, 'nombre', 'Conjunto Residencial'))
            
            # Preparar el contexto para el template
            context = {
                'nombre': nombre_limpio,
                'mensaje': mensaje_usuario,
                'fecha': datetime.now().strftime('%d/%m/%Y'),
                'conjunto': request.user.conjunto
            }
            
            # Versión en texto plano del mensaje - SANITIZADA
            mensaje_plain = mensaje_usuario.replace('<br>', '\n')
            plain_content = sanitize_text(f"""
Estimado/a {nombre_limpio},

{mensaje_plain}

Atentamente,
Administración Conjunto Residencial

---------------------------------------------
Teléfono: (601) XXX-XXXX
Email: admin@conjunto.com
Horario: Lunes a Viernes de 8:00 AM a 6:00 PM
         Sábados de 9:00 AM a 1:00 PM

© 2024 Administración Conjunto Residencial
Recibió este email porque está registrado como propietario.
""")
            
            # Renderizar plantilla HTML
            try:
                html_content = render_to_string('emails/general_notification.html', context)
                html_content = sanitize_text(html_content)
                logger.debug("Plantilla HTML renderizada correctamente")
            except Exception as e:
                logger.warning(f"Error al renderizar plantilla: {str(e)}. Usando plantilla alternativa.")
                
                html_content = sanitize_text(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notificación</title>
</head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background-color:#f7f9fc;color:#333;">
    <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
        <div style="background:linear-gradient(45deg,#6015ab,#ffaf19);padding:25px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:24px;font-weight:600;">Notificación General</h1>
        </div>
        <div style="padding:30px;">
            <p style="font-size:16px;margin-bottom:25px;">Estimado(a) <strong>{nombre_limpio}</strong>,</p>
            <div style="background:#f8f9fd;border-left:4px solid #6015ab;padding:20px;margin:25px 0;border-radius:4px;">
                {mensaje_usuario}
            </div>
            <div style="margin-top:30px;padding-top:20px;border-top:1px solid #eee;">
                <p style="margin:5px 0;">Atentamente,</p>
                <p style="font-weight:bold;font-size:16px;color:#333;">Administración {conjunto_nombre_limpio}</p>
            </div>
        </div>
        <div style="background:#333;color:#fff;padding:20px;text-align:center;">
            <p style="margin:5px 0;font-size:13px;">© 2024 Administración {conjunto_nombre_limpio}</p>
        </div>
    </div>
</body>
</html>
""")

            # Crear mensaje de correo con AWS SES
            email = EmailMultiAlternatives(
                subject='Notificación General',
                body=plain_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_limpio],
                bcc=[sanitize_text(prop['email']) for prop in other_props]
            )
            
            # Adjuntar versión HTML
            email.attach_alternative(html_content, "text/html")
            
            # Agregar archivos adjuntos
            for attachment in attachments_data:
                email.attach(
                    attachment['filename'],
                    attachment['content'],
                    attachment['content_type']
                )

            # 7. Enviar lote
            try:
                email.send(fail_silently=False)
                total_enviados += len(batch)
                logger.info(f"Lote {batch_num}/{total_lotes} enviado: {len(batch)} destinatarios. Total: {total_enviados}/{total_propietarios}")
            except Exception as e:
                logger.error(f"Error enviando lote {batch_num}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                continue

        # 8. Retornar resultado
        if total_enviados > 0:
            success_message = f"Se enviaron {total_enviados} de {total_propietarios} notificaciones"
            
            if attachments_data:
                archivo_texto = "archivo" if len(attachments_data) == 1 else "archivos"
                success_message += f" con {len(attachments_data)} {archivo_texto} adjuntos ({round(total_size/(1024*1024), 2)}MB)"
            
            logger.info(success_message)
            
            return JsonResponse({
                'status': 'success',
                'enviados': total_enviados,
                'total': total_propietarios,
                'files_attached': len(attachments_data),
                'total_size_mb': round(total_size/(1024*1024), 2)
            })
        else:
            logger.error("No se pudo completar el envío de mensajes")
            return JsonResponse({
                'status': 'error',
                'message': 'No se pudo completar el envío de mensajes'
            })

    except Exception as e:
        logger.error(f"Error general en procesar_envio: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': f'Error en el sistema: {str(e)}'
        })

# views.py --- notification individual


@require_http_methods(["POST"])
@login_required
@role_required(['porteria', 'administrador'])
def enviar_notificacion_individual(request):
    """
    Vista para enviar notificaciones individuales a propietarios según su ubicación.
    """
    logger.info("Iniciando envío de notificación individual")
    try:
        # Extraer datos de la solicitud
        torre_id = request.POST.get('torre_id')
        apartamento = request.POST.get('apartamento')
        mensaje = request.POST.get('message')
        
        mensaje = sanitize_text(mensaje) if mensaje else ''

        # Validar datos
        if not torre_id or not apartamento or not mensaje:
            logger.warning("Datos de notificación individual incompletos")
            return JsonResponse({
                'status': 'error', 
                'message': 'Todos los campos son requeridos'
            }, status=400)
        
        # Obtener la torre
        try:
            torre = Torre.objects.get(
                id=torre_id,
                conjunto=request.user.conjunto,
                activo=True
            )
        except Torre.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'La torre seleccionada no existe o no pertenece a su conjunto'
            }, status=404)
        
        # Buscar propietarios que coincidan con la ubicación
        propietarios = Usuario.objects.filter(
            user_type='propietario',
            is_active=True,
            conjunto=request.user.conjunto,
            torre=torre,
            apartamento=apartamento
        )
        
        if not propietarios.exists():
            logger.warning(f"No se encontraron propietarios en {torre.nombre} - Apto {apartamento}")
            return JsonResponse({
                'status': 'error',
                'message': f"No se encontraron propietarios en la ubicación especificada"
            }, status=404)
        
        # Procesar archivos adjuntos
        from django.core.mail import EmailMultiAlternatives
        
        archivos_data = []
        for file in request.FILES.getlist('files[]'):
            # Verificar tamaño
            if file.size > 10 * 1024 * 1024:  # 10MB
                return JsonResponse({
                    'status': 'error',
                    'message': f'El archivo {file.name} supera el límite de 10MB'
                }, status=400)
            
            archivo_contenido = file.read()
            archivos_data.append({
                'filename': file.name,
                'content': archivo_contenido,
                'content_type': file.content_type
            })
            
            logger.info(f"Archivo adjunto procesado: {file.name} ({file.size/(1024*1024):.2f}MB)")
        
        # Enviar notificación a cada propietario
        enviados = 0
        for propietario in propietarios:
            try:
                # Preparar contexto para la plantilla
                context = {
                    'nombre_propietario': propietario.nombre,
                    'torre': torre.nombre,
                    'apartamento': apartamento,
                    'mensaje': mensaje,
                    'year': datetime.now().year,
                    'nombre_conjunto': request.user.conjunto.nombre,
                    'archivos': [] 
                }
                
                # Renderizar plantilla HTML
                try:
                    html_content = render_to_string('emails/individual_notification.html', context)
                except Exception as e:
                    logger.warning(f"Error al renderizar plantilla: {str(e)}. Usando plantilla alternativa.")
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    </head>
                    <body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f5f7fa;">
                        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:20px;">
                            <h2 style="color:#6015ab;">Notificación Individual</h2>
                            <p>Estimado(a) {propietario.nombre},</p>
                            <p>{mensaje}</p>
                            <p>Esta notificación es exclusiva para su apartamento: {propietario.get_ubicacion_completa()}</p>
                            <p>Atentamente,<br>Administración {request.user.conjunto.nombre}</p>
                        </div>
                    </body>
                    </html>
                    """
                
                # Versión texto plano
                mensaje_plain_ind = mensaje.replace('<br>', '\n')
                plain_content = f"""
                Estimado/a {propietario.nombre},

                {mensaje_plain_ind}
                
                Esta notificación es exclusiva para su apartamento: {propietario.get_ubicacion_completa()}
                
                Atentamente,
                Administración {request.user.conjunto.nombre}
                
                ---------------------------------------------
                {request.user.conjunto.nombre}
                Teléfono: {request.user.conjunto.telefono or "(No disponible)"}
                Email: {request.user.conjunto.email_contacto or "(No disponible)"}
                """
                
                # Crear y enviar email
                msg = EmailMultiAlternatives(
                    subject='Notificación Individual para su Apartamento',
                    body=plain_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[propietario.email]
                )
                msg.attach_alternative(html_content, "text/html")
                
                # Agregar archivos adjuntos
                for archivo in archivos_data:
                    msg.attach(
                        archivo['filename'],
                        archivo['content'],
                        archivo['content_type']
                    )
                
                # Enviar correo
                msg.send(fail_silently=False)
                enviados += 1
                logger.info(f"Notificación individual enviada a {propietario.email}")
                
            except Exception as e:
                logger.error(f"Error procesando notificación para {propietario.email}: {str(e)}")
                continue
        
        # Construir respuesta
        if enviados > 0:
            return JsonResponse({
                'status': 'success',
                'message': f'Notificación enviada exitosamente a {enviados} propietario(s)',
                'enviados': enviados,
                'total': propietarios.count(),
                'ubicacion': f"{torre.nombre} - Apto {apartamento}"
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'No se pudo enviar la notificación a ningún propietario'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error general en enviar_notificacion_individual: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error en el servidor: {str(e)}'
        }, status=500)



# views.py --- s.Publicos


BATCH_SIZE = 500  # Tamaño del lote
DELAY_BETWEEN_BATCHES = 2  # Segundos entre lotes

@login_required
@csrf_protect
@require_POST
def send_service_notification(request):
    """
    Envía notificaciones sobre disponibilidad de servicios públicos a los propietarios.
    """
    try:
        # Validar que la petición sea JSON
        if not request.content_type == 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Content-Type debe ser application/json'
            }, status=400)

        data = json.loads(request.body)
        service_type = data.get('service_type')

        service_type = sanitize_text(service_type) if service_type else ''
        
        if not service_type:
            return JsonResponse({
                'status': 'error',
                'message': 'Tipo de servicio no especificado'
            }, status=400)

        # Obtener el conjunto actual del usuario logueado
        conjunto_actual = request.user.conjunto

        # Filtrar propietarios solo del conjunto actual
        propietarios = Usuario.objects.filter(
            user_type='propietario',
            is_active=True,
            conjunto=conjunto_actual
        ).values('email', 'nombre')

        total_users = propietarios.count()

        if total_users == 0:
            return JsonResponse({
                'status': 'error',
                'message': f'No hay propietarios activos para enviar notificaciones en el conjunto {conjunto_actual.nombre}'
            }, status=404)

        from django.core.mail import EmailMultiAlternatives
        
        successful_sends = 0
        failed_sends = 0
        errors = []

        # Dividir en lotes
        BATCH_SIZE = 500
        DELAY_BETWEEN_BATCHES = 2
        propietarios_list = list(propietarios)
        batches = [propietarios_list[i:i + BATCH_SIZE] for i in range(0, total_users, BATCH_SIZE)]
        total_batches = len(batches)
        
        # Registrar inicio del proceso
        logger.info(f"Iniciando envío de notificaciones de {service_type} a {total_users} propietarios en {total_batches} lotes")

        for batch_index, batch in enumerate(batches, 1):
            batch_successful = 0
            batch_failed = 0

            for propietario in batch:
                try:
                    email = propietario['email']
                    nombre = propietario['nombre']
                    
                    # Preparar contexto para la plantilla
                    context = {
                        'nombre': nombre,
                        'service_type': service_type,
                        'fecha': datetime.now().strftime('%d/%m/%Y'),
                        'conjunto': conjunto_actual
                    }
                    
                    # Crear contenido HTML utilizando la plantilla
                    try:
                        html_content = render_to_string('emails/service_notification.html', context)
                        logger.debug(f"Plantilla HTML renderizada correctamente para {email}")
                    except Exception as e:
                        logger.warning(f"Error al renderizar plantilla: {str(e)}. Usando plantilla alternativa.")
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f5f7fa;">
                            <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:20px;">
                                <h2 style="color:#6015ab;">Notificación de {service_type}</h2>
                                <p>Estimado(a) {nombre},</p>
                                <p>Su factura de {service_type} está disponible para retiro en portería.</p>
                                <p>Por favor, pase a retirarla en horario de atención.</p>
                                <p>Atentamente,<br>Administración Conjunto Residencial</p>
                            </div>
                        </body>
                        </html>
                        """
                    
                    # Crear versión texto plano
                    plain_content = f"""
Estimado/a {nombre},

Su factura de {service_type} está disponible para retiro en portería.
Por favor, pase a retirarla en horario de atención.

Atentamente,
Administración Conjunto Residencial

---------------------------------------------
Teléfono: (601) XXX-XXXX
Email: admin@conjunto.com
Horario: Lunes a Viernes de 8:00 AM a 6:00 PM
         Sábados de 9:00 AM a 1:00 PM

© 2024 Administración Conjunto Residencial
"""

                    # Crear y enviar email con AWS SES
                    msg = EmailMultiAlternatives(
                        subject=f'Notificación: Su factura de {service_type} está disponible',
                        body=plain_content,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[email]
                    )
                    msg.attach_alternative(html_content, "text/html")
                    
                    msg.send(fail_silently=False)
                    batch_successful += 1
                    successful_sends += 1
                    logger.debug(f"Email enviado exitosamente a {email}")

                except Exception as e:
                    email_for_log = propietario.get('email', 'unknown_email')
                    batch_failed += 1
                    failed_sends += 1
                    errors.append({
                        'email': email_for_log,
                        'error': str(e),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    logger.error(f"Excepción al enviar email a {email_for_log}: {str(e)}")

            # Calcular y registrar progreso del lote
            progress = (batch_index / total_batches) * 100
            logger.info(f"Lote {batch_index}/{total_batches}: {progress:.1f}% completado. "
                      f"Exitosos: {batch_successful}, Fallidos: {batch_failed}")

            # Esperar entre lotes
            if batch_index < total_batches:
                time.sleep(DELAY_BETWEEN_BATCHES)

        # Preparar respuesta final
        final_response = {
            'status': 'success' if successful_sends > 0 else 'error',
            'message': f'Proceso completado: {successful_sends} exitosos, {failed_sends} fallidos',
            'successful_sends': successful_sends,
            'failed_sends': failed_sends,
            'total_processed': total_users,
            'completion_percentage': 100,
            'service_type': service_type
        }
        
        if errors:
            final_response['errors_sample'] = errors[:5] if len(errors) > 5 else errors
            
        logger.info(f"Envío de notificaciones de {service_type} completado: {successful_sends} exitosos, {failed_sends} fallidos")
        return JsonResponse(final_response)

    except json.JSONDecodeError:
        logger.error("Error en el formato de la petición JSON")
        return JsonResponse({
            'status': 'error',
            'message': 'Error en el formato de la petición JSON'
        }, status=400)
    except Exception as e:
        logger.error(f"Error general en send_service_notification: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error en el servidor: {str(e)}',
            'successful_sends': successful_sends if 'successful_sends' in locals() else 0,
            'failed_sends': failed_sends if 'failed_sends' in locals() else 0,
            'total_processed': total_users if 'total_users' in locals() else 0
        }, status=500)

@login_required
@role_required(['porteria', 'administrador'])
def leerscaner(request):
    return render(request, 'leer_scaner.html')

@login_required
@role_required(['porteria', 'administrador'])
def noti_generales(request):
    return render(request, 'noti_generales.html')

@login_required
@role_required(['porteria', 'administrador'])
def noti_publicos(request):
    return render(request, 'noti_publicos.html')

@login_required
@role_required(['porteria', 'administrador'])
def noti_individual(request):
    return render(request, 'noti_individual.html')

@login_required
@role_required(['porteria', 'administrador'])
def notificaciones(request):
    return render(request, 'notificaciones.html')


@login_required
@role_required(['propietario'])
def historial_visitantes(request):
    """Vista para que el propietario vea los visitantes de su apartamento."""
    apartamento = request.user.apartamento
    conjunto_id = request.user.conjunto_id

    # Filtros opcionales
    fecha_desde = request.GET.get('desde')
    fecha_hasta = request.GET.get('hasta')

    visitantes = Visitante.objects.filter(
        conjunto_id=conjunto_id,
        numper=apartamento,
    ).order_by('-fecha_generacion')

    if fecha_desde:
        try:
            visitantes = visitantes.filter(
                fecha_generacion__date__gte=datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            )
        except ValueError:
            pass

    if fecha_hasta:
        try:
            visitantes = visitantes.filter(
                fecha_generacion__date__lte=datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            )
        except ValueError:
            pass

    return render(request, 'historial_visitantes.html', {
        'visitantes': visitantes,
        'apartamento': apartamento,
        'fecha_desde': fecha_desde or '',
        'fecha_hasta': fecha_hasta or '',
    })


@login_required
@role_required(['porteria', 'administrador', 'propietario'])
def parking(request):
    return render(request, 'parking/inicio_parqueo.html')


@login_required
def zonas_comunes(request):
    return render(request, 'zonas_comunes.html')


_fernet_key = os.environ.get('FERNET_KEY') or getattr(settings, 'FERNET_KEY', None)
if not _fernet_key:
    raise RuntimeError('FERNET_KEY no configurado en variables de entorno')
cipher = Fernet(_fernet_key.encode())


@login_required
def bienvenida(request):
    print("🔥🔥🔥 BIENVENIDA FUNCTION CALLED 🔥🔥🔥")
    print(f"REQUEST METHOD: {request.method}")
    if request.method == 'POST':
        print("🔥🔥🔥 INSIDE POST 🔥🔥🔥")
        try:
            print("🔥🔥🔥 INSIDE TRY 🔥🔥🔥")
            with transaction.atomic():
                # Generar token único
                uuid_token = str(uuid.uuid4())
                
                # Obtener el tipo de visitante
                tipo_visitante = request.POST.get('tipo_visitante', 'peatonal')
                
                # Datos comunes para ambos tipos de visitantes
                datos_visitante = {
                    'email': sanitize_text(request.POST.get('email', '')),
                    'nombre': sanitize_text(request.POST.get('nombre', '')),
                    'celular': sanitize_text(request.POST.get('celular', '')),
                    'cedula': sanitize_text(request.POST.get('cedula', '')),
                    'motivo': sanitize_text(request.POST.get('motivo', '')),
                    'email_creador': request.user.email,
                    'nombre_log': sanitize_text(request.POST.get('nombre_log', '')),
                    'token': uuid_token,
                    'fecha_generacion': timezone.now(),
                    'numper': sanitize_text(request.POST.get('numper', '')),
                    'conjunto_id': request.user.conjunto_id,
                    'ultima_lectura': None
                }
                
                # Crear el visitante según el tipo
                if tipo_visitante == 'vehicular':
                    visitante = VisitanteVehicular.objects.create(
                        **datos_visitante,
                        tipo_vehiculo=sanitize_text(request.POST.get('tipo_vehiculo', '')),
                        placa=sanitize_text(request.POST.get('placa', '')).upper(),
                        segunda_lectura=None
                    )
                else:
                    visitante = Visitante.objects.create(**datos_visitante)
                
                logger.info(f"Visitante {tipo_visitante} creado - ID: {visitante.id}")
                log_audit(request, 'visitante_creado',
                          f"Tipo: {tipo_visitante} | Nombre: {visitante.nombre} | ID: {visitante.id}")

                # Generar y enviar QR
                raw_token = f"Kislev_{tipo_visitante}_{uuid_token}"  # Incluimos el tipo en el token
                encrypted_token = cipher.encrypt(raw_token.encode()).decode()
                
                # Generar URL del QR - Ahora siempre usa validar_qr
                base_url = f"https://{request.get_host()}" if 'railway.app' in request.get_host() else request.build_absolute_uri('/').rstrip('/')
                enlace_qr = f"{base_url}{reverse('validar_qr', args=[encrypted_token])}"

                # Generar QR en memoria (sin tocar disco)
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
                qr.add_data(enlace_qr)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_buffer = BytesIO()
                qr_img.save(qr_buffer, format='PNG')
                qr_buffer.seek(0)

                logger.info(f"QR generado en memoria para visitante {visitante.id}")

                # Preparar mensaje de email según tipo de visitante
                mensaje_adicional = ""
                if tipo_visitante == 'vehicular':
                    mensaje_adicional = f"\n\nNota: Este código QR es válido para registrar tanto la entrada como la salida del vehículo."

                # INICIO DE LOGS
                logger.info("=" * 50)
                logger.info("INICIANDO ENVÍO DE EMAIL CON QR")
                logger.info(f"Visitante ID: {visitante.id}")
                logger.info(f"Visitante nombre: {visitante.nombre}")
                logger.info(f"Visitante email: {visitante.email}")
                logger.info("QR generado en memoria (BytesIO)")
                logger.info(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
                logger.info(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
                logger.info("=" * 50)
                # FIN DE LOGS

                # Enviar email
                try:
                    # Sanitizar todos los datos antes de enviar
                    nombre_limpio = sanitize_text(visitante.nombre)
                    email_limpio = sanitize_text(visitante.email)
                    mensaje_limpio = sanitize_text(mensaje_adicional) if mensaje_adicional else ""
                    
                    # LOGS ADICIONALES
                    logger.info(f"Datos sanitizados:")
                    logger.info(f"  - nombre_limpio: {nombre_limpio}")
                    logger.info(f"  - email_limpio: {email_limpio}")
                    logger.info(f"  - mensaje_limpio: {mensaje_limpio}")
                    
                    logger.info("Creando EmailMessage...")
                    # FIN LOGS ADICIONALES
                    
                    email_message = EmailMessage(
                        sanitize_text("Tu Codigo QR de Visitante"),
                        sanitize_text(f"Hola {nombre_limpio},\n\nAdjunto encontraras tu codigo QR para la visita.{mensaje_limpio}"),
                        sanitize_text(settings.DEFAULT_FROM_EMAIL),
                        [email_limpio]
                    )
                    
                    email_message.attach(f'qr_{visitante.id}.png', qr_buffer.getvalue(), 'image/png')

                    logger.info("Enviando email...")
                    result = email_message.send()
                    logger.info(f"Email enviado. Resultado: {result}")
                    logger.info(f"✓ QR enviado exitosamente a {email_limpio}")
                    
                except Exception as e:
                    logger.error("!" * 50)
                    logger.error(f"ERROR ENVIANDO EMAIL: {str(e)}")
                    logger.error(f"Tipo de error: {type(e).__name__}")
                    import traceback
                    logger.error(f"Traceback completo:")
                    logger.error(traceback.format_exc())
                    logger.error("!" * 50)

                logger.info("Proceso de envío de email completado")

                email_b64 = base64.urlsafe_b64encode(visitante.email.encode()).decode()
                redirect_url = reverse('valqr', kwargs={'email_b64': email_b64})
                
                # Si es una petición AJAX, devolver JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'redirect_url': redirect_url,
                        'message': 'QR generado exitosamente'
                    })
                
                # Si no es AJAX, redireccionar normalmente
                return redirect('valqr', email_b64=email_b64)

        except Exception as e:
            logger.error(f"Error en bienvenida: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=400)
            messages.error(request, 'Error al generar el QR. Por favor, intente nuevamente.')
            return render(request, 'bienvenida.html', {'error': str(e)})

    return render(request, 'bienvenida.html')




@login_required
@role_required(['porteria', 'administrador'])
def validar_qr(request, encrypted_token):
    logger.info("Iniciando validación de QR")
    
    # Verificar si es una pre-carga de Safari/iOS
    is_ios_prefetch = (
        'purpose' in request.headers and 
        request.headers['purpose'] == 'prefetch'
    ) or (
        'Sec-Purpose' in request.headers and 
        request.headers['Sec-Purpose'] == 'prefetch'
    )

    if is_ios_prefetch:
        logger.info("Detectada pre-carga de iOS - ignorando validación")
        return HttpResponse(status=204)

    source = request.GET.get('source', '')
    if source != 'scan':
        logger.warning("Intento de acceso sin escaneo")
        return render(request, 'error_qr.html', {
            'mensaje': 'Acceso no autorizado. Escanea el QR desde la aplicación.'
        })

    try:
        # Desencriptar token
        decrypted_token = cipher.decrypt(encrypted_token.encode()).decode()
        if not decrypted_token.startswith("Kislev_"):
            logger.error("Token inválido: prefijo incorrecto")
            return render(request, 'error_qr.html', {'mensaje': 'Token no válido.'})

        # Extraer tipo y token
        parts = decrypted_token[len("Kislev_"):].split('_', 1)
        if len(parts) != 2:
            logger.error("Token inválido: formato incorrecto")
            return render(request, 'error_qr.html', {'mensaje': 'Token no válido.'})

        tipo_visitante, original_token = parts
        
        # Obtener visitante con bloqueo según tipo
        with transaction.atomic():
            if tipo_visitante == 'vehicular':
                visitante = get_object_or_404(
                    VisitanteVehicular.objects.select_for_update(nowait=True),
                    token=original_token
                )
            else:
                visitante = get_object_or_404(
                    Visitante.objects.select_for_update(nowait=True),
                    token=original_token
                )
            
            visitante.refresh_from_db()
            
            # Lógica específica para visitantes vehiculares
            if tipo_visitante == 'vehicular':
                if visitante.segunda_lectura:
                    return render(request, 'qr_desactivado.html', {
                        'mensaje': 'Este código QR ya completó sus dos lecturas.',
                        'ultima_lectura': visitante.segunda_lectura
                    })
                
                tiempo_actual = timezone.now()
                if not visitante.ultima_lectura:
                    # Primera lectura (entrada)
                    visitante.ultima_lectura = tiempo_actual
                    mensaje = "Entrada registrada"
                else:
                    # Segunda lectura (salida)
                    visitante.segunda_lectura = tiempo_actual
                    mensaje = "Salida registrada"
                
                visitante.nombre_log = request.user.email
                visitante.save()
                log_audit(request, 'qr_validado',
                          f"Vehicular | {mensaje} | Visitante: {visitante.nombre} | Placa: {visitante.placa}")

            # Lógica para visitantes peatonales
            else:
                # Verificación especial para Safari/iOS
                is_safari = 'Safari' in request.headers.get('User-Agent', '')
                if is_safari and visitante.ultima_lectura is not None:
                    ultima_lectura = timezone.localtime(visitante.ultima_lectura)
                    tiempo_actual = timezone.localtime(timezone.now())
                    if (tiempo_actual - ultima_lectura).total_seconds() < 5:
                        return render(request, 'validar_qr.html', {'visitante': visitante})

                if visitante.ultima_lectura is not None:
                    return render(request, 'qr_desactivado.html', {
                        'mensaje': 'Este código QR ya ha sido utilizado.',
                        'ultima_lectura': visitante.ultima_lectura
                    })

                tiempo_actual = timezone.now()
                visitante.ultima_lectura = tiempo_actual
                visitante.nombre_log = request.user.email
                visitante.save()
                mensaje = "Visita registrada"
                log_audit(request, 'qr_validado',
                          f"Peatonal | Visitante: {visitante.nombre} | Cédula: {visitante.cedula}")

            # Enviar notificación por email
            try:
                email_subject = "Registro de visitante"
                if tipo_visitante == 'vehicular':
                    email_subject = f"Registro vehicular - {mensaje}"
                
                email_body = f"""
                Hola,
                
                Tu visitante {visitante.nombre} {mensaje.lower()}.
                Fecha y hora: {timezone.localtime(visitante.ultima_lectura).strftime('%Y-%m-%d %H:%M:%S')}
                """

                if tipo_visitante == 'vehicular':
                    email_body += f"""
                    Vehículo: {visitante.get_tipo_vehiculo_display()}
                    Placa: {visitante.placa}
                    """

                email_body += f"""
                Motivo de la visita: {visitante.motivo}
                
                Saludos,
                Kislev
                """
                
                email = EmailMessage(
                    email_subject,
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [visitante.email_creador],
                    headers={'X-Priority': '1'}
                )
                email.send(fail_silently=False)
                logger.info(f"Notificación enviada a {visitante.email_creador}")
            except Exception as e:
                logger.error(f"Error enviando notificación por email: {str(e)}")

            return render(request, 'validar_qr.html', {
                'visitante': visitante,
                'mensaje': mensaje
            })

    except Exception as e:
        logger.error(f"Error procesando QR: {str(e)}")
        return render(request, 'error_qr.html', {
            'mensaje': f'Error al procesar el QR: {str(e)}'
        })
        
        
        

@login_required
def success_page(request, email_b64):
    try:
        # Decodificar el email
        email = base64.urlsafe_b64decode(email_b64.encode()).decode()
        
        # Obtener información del usuario
        nombre_usuario = request.user.phone_number
        user_type = request.user.user_type
        
        context = {
            'nombre': nombre_usuario,
            'user_type': user_type,
            'email': email
        }
        
        return render(request, 'valqr.html', context)  # Ya no necesitas 'salas/'
        
    except Exception as e:
        print(f"Error en success_page: {e}")
        # Podrías redirigir a una página de error o mostrar un mensaje
        return render(request, 'valqr.html', {
            'error': 'Ocurrió un error al procesar la solicitud'
        })



# Dashboard 




@login_required
@role_required(['administrador'])
def dashboard(request):
    try:
        # Obtener el conjunto_id del usuario logueado
        conjunto_id = request.user.conjunto_id

        # Configuración inicial de fechas
        fecha_actual = timezone.localtime(timezone.now()).date()
        año_actual = fecha_actual.year
        años_disponibles = [año_actual, año_actual - 1, año_actual - 2]

        # Obtener fecha y año seleccionados
        fecha_seleccionada = request.GET.get('fecha')
        año_seleccionado = request.GET.get('año')

        # Procesar fecha seleccionada
        try:
            if fecha_seleccionada:
                fecha_base = datetime.strptime(fecha_seleccionada, '%Y-%m-%d')
                fecha_inicio = timezone.make_aware(
                    datetime.combine(fecha_base.date(), time.min)
                )
                fecha_fin = timezone.make_aware(
                    datetime.combine(fecha_base.date(), time.max)
                )
            else:
                fecha_inicio = timezone.make_aware(
                    datetime.combine(fecha_actual, time.min)
                )
                fecha_fin = timezone.make_aware(
                    datetime.combine(fecha_actual, time.max)
                )
        except ValueError:
            fecha_inicio = timezone.make_aware(
                datetime.combine(fecha_actual, time.min)
            )
            fecha_fin = timezone.make_aware(
                datetime.combine(fecha_actual, time.max)
            )

        # Procesar año seleccionado
        try:
            if año_seleccionado:
                año_seleccionado = int(año_seleccionado)
            else:
                año_seleccionado = año_actual
        except ValueError:
            año_seleccionado = año_actual

        # Consultas base - Filtradas por conjunto_id
        visitantes_dia = Visitante.objects.filter(
            fecha_generacion__range=(fecha_inicio, fecha_fin),
            conjunto_id=conjunto_id
        )

        # Análisis de visitantes recurrentes - Filtrado por conjunto
        correos_recurrentes = Visitante.objects.filter(
            conjunto_id=conjunto_id
        ).values('email').annotate(
            total=Count('email')
        ).filter(total__gt=1).values_list('email', flat=True)

        # Conteos para el día seleccionado
        visitantes_recurrentes = visitantes_dia.filter(email__in=correos_recurrentes).count()
        visitantes_nuevos = visitantes_dia.exclude(email__in=correos_recurrentes).count()
        ingresos = visitantes_dia.exclude(ultima_lectura=None).count()

        # Calcular pendientes incluyendo las últimas 24 horas
        tiempo_limite = timezone.now() - timedelta(hours=24)

        # Pendientes del día actual
        pendientes_hoy = visitantes_dia.filter(ultima_lectura=None).count()

        # Pendientes anteriores pero aún válidos (dentro de 24 horas)
        pendientes_anteriores = Visitante.objects.filter(
            ultima_lectura=None,
            fecha_generacion__lt=fecha_inicio,
            fecha_generacion__gte=tiempo_limite,
            conjunto_id=conjunto_id
        ).count()

        # Total de pendientes
        total_pendientes = pendientes_hoy + pendientes_anteriores

        # Datos para el gráfico por año seleccionado
        año_inicio = timezone.make_aware(datetime(año_seleccionado, 1, 1))
        año_fin = timezone.make_aware(datetime(año_seleccionado, 12, 31, 23, 59, 59))
        
        visitantes_por_mes = Visitante.objects.filter(
            ultima_lectura__isnull=False,
            ultima_lectura__range=(año_inicio, año_fin),
            conjunto_id=conjunto_id
        ).annotate(
            mes=ExtractMonth('ultima_lectura')
        ).values('mes').annotate(
            total=Count('id')
        ).order_by('mes')

        # Preparar datos del gráfico
        meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        datos_grafico = [0] * 12
        for item in visitantes_por_mes:
            datos_grafico[item['mes']-1] = item['total']

        # Obtener visitantes por motivo y día
        visitantes_por_motivo = visitantes_dia.values('motivo').annotate(
            total=Count('id')
        ).order_by('-total')

        # Total de visitantes por día
        total_visitantes_dia = visitantes_dia.count()
        
        # ── Datos financieros ──────────────────────────────────────────
        mes_actual = fecha_actual.month
        cuotas_qs = Cuota.objects.filter(conjunto_id=conjunto_id)
        pagos_mes = Pago.objects.filter(
            cuota__conjunto_id=conjunto_id,
            fecha_pago__year=año_seleccionado,
            fecha_pago__month=mes_actual,
        )
        total_propietarios_fin = Usuario.objects.filter(
            conjunto_id=conjunto_id, user_type='propietario', is_active=True
        ).count()
        cuotas_vigentes = cuotas_qs.filter(fecha_vencimiento__gte=fecha_actual)
        cuotas_vencidas = cuotas_qs.filter(fecha_vencimiento__lt=fecha_actual)
        recaudo_mes = pagos_mes.aggregate(
            total=models.Sum('monto_pagado')
        )['total'] or 0
        propietarios_al_dia = Pago.objects.filter(
            cuota__conjunto_id=conjunto_id,
            cuota__fecha_vencimiento__gte=fecha_actual,
        ).values('propietario_id').distinct().count()
        pct_al_dia = round(
            (propietarios_al_dia / total_propietarios_fin * 100)
            if total_propietarios_fin else 0
        )
        # Recaudo por mes del año seleccionado
        recaudo_por_mes = [0] * 12
        for p in Pago.objects.filter(
            cuota__conjunto_id=conjunto_id,
            fecha_pago__year=año_seleccionado,
        ).values('fecha_pago__month').annotate(total=models.Sum('monto_pagado')):
            recaudo_por_mes[p['fecha_pago__month'] - 1] = p['total'] or 0

        # ── Datos novedades ────────────────────────────────────────────
        from django.db.models import Sum as _Sum
        mes_inicio = fecha_actual.replace(day=1)
        novedades_mes = Novedad.objects.filter(conjunto_id=conjunto_id, activa=True, created_at__date__gte=mes_inicio)
        nov_total = Novedad.objects.filter(conjunto_id=conjunto_id, activa=True).count()
        nov_mes = novedades_mes.count()
        from .models import LikeNovedad, ComentarioNovedad
        nov_likes = LikeNovedad.objects.filter(novedad__conjunto_id=conjunto_id).count()
        nov_comentarios = ComentarioNovedad.objects.filter(novedad__conjunto_id=conjunto_id).count()
        ultimas_novedades = Novedad.objects.filter(
            conjunto_id=conjunto_id, activa=True
        ).order_by('-created_at')[:3]

        # Contexto para el template
        context = {
            'fecha_seleccionada': fecha_inicio.date(),
            'fecha_actual': fecha_actual,
            'ingresos': ingresos,
            'pendientes_hoy': pendientes_hoy,
            'pendientes_anteriores': pendientes_anteriores,
            'total_pendientes': total_pendientes,
            'visitantes_recurrentes': visitantes_recurrentes,
            'visitantes_nuevos': visitantes_nuevos,
            'meses': meses,
            'datos_grafico': datos_grafico,
            'años_disponibles': años_disponibles,
            'año_seleccionado': año_seleccionado,
            'visitantes_por_motivo': visitantes_por_motivo,
            'total_visitantes_dia': total_visitantes_dia,
            'conjunto': request.user.conjunto,
            'conjunto_id': conjunto_id,
            # Financiero
            'recaudo_mes': recaudo_mes,
            'cuotas_vigentes': cuotas_vigentes.count(),
            'cuotas_vencidas': cuotas_vencidas.count(),
            'propietarios_al_dia': propietarios_al_dia,
            'total_propietarios_fin': total_propietarios_fin,
            'pct_al_dia': pct_al_dia,
            'recaudo_por_mes': recaudo_por_mes,
            # Novedades
            'nov_total': nov_total,
            'nov_mes': nov_mes,
            'nov_likes': nov_likes,
            'nov_comentarios': nov_comentarios,
            'ultimas_novedades': ultimas_novedades,
            # Paquetes
            'paq_pendientes': Paquete.objects.filter(conjunto_id=conjunto_id, estado='pendiente').count(),
            'paq_hoy_registrados': Paquete.objects.filter(conjunto_id=conjunto_id, fecha_registro__date=fecha_actual).count(),
            'paq_hoy_entregados': Paquete.objects.filter(conjunto_id=conjunto_id, fecha_entrega__date=fecha_actual).count(),
            'torres_dashboard': Torre.objects.filter(conjunto_id=conjunto_id, activo=True),
            # Reservas pendientes de aprobación (solo de propietarios)
            'reservas_pendientes': Reserva.objects.filter(
                sala__conjunto_id=conjunto_id, estado='pendiente'
            ).exclude(usuario__user_type='administrador').select_related('sala', 'usuario').order_by('fecha', 'hora_inicio'),
            'reservas_pendientes_count': Reserva.objects.filter(
                sala__conjunto_id=conjunto_id, estado='pendiente'
            ).exclude(usuario__user_type='administrador').count(),
        }
        
        return render(request, 'dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error en dashboard: {str(e)}")
        messages.error(request, f"Error al cargar el dashboard: {str(e)}")
        return render(request, 'dashboard.html', {
            'error': 'Error al cargar el dashboard',
            'conjunto': request.user.conjunto,
            'conjunto_id': request.user.conjunto_id
        })


#consulta por hora
def get_visitor_stats(request):
    # Obtener el conjunto_id del usuario logueado
    conjunto_id = request.user.conjunto_id
    
    # Obtener el tipo de filtro desde la solicitud
    filter_type = request.GET.get('filter_type', 'week')
    selected_month = int(request.GET.get('month', datetime.now().month))
    selected_year = int(request.GET.get('year', datetime.now().year))
    
    # Consulta base filtrada por conjunto
    base_query = Visitante.objects.filter(
        conjunto_id=conjunto_id
    ).exclude(ultima_lectura__isnull=True)
    
    if filter_type == 'week':
        # Consulta por día de la semana
        stats = base_query.annotate(
            day=ExtractWeekDay('ultima_lectura')
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')
        
        # Mapear números a nombres de días
        days_map = {
            1: 'Domingo',
            2: 'Lunes',
            3: 'Martes',
            4: 'Miércoles',
            5: 'Jueves',
            6: 'Viernes',
            7: 'Sábado'
        }
        
        all_data = {day: 0 for day in range(1, 8)}
        for stat in stats:
            all_data[stat['day']] = stat['count']
        
        labels = [days_map[day] for day in range(1, 8)]
        data = [all_data[day] for day in range(1, 8)]
        
    elif filter_type == 'month':
        # Consulta por mes
        stats = base_query.filter(
            ultima_lectura__year=selected_year
        ).annotate(
            month=ExtractMonth('ultima_lectura')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        months_map = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo',
            4: 'Abril', 5: 'Mayo', 6: 'Junio',
            7: 'Julio', 8: 'Agosto', 9: 'Septiembre',
            10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        
        all_data = {month: 0 for month in range(1, 13)}
        for stat in stats:
            all_data[stat['month']] = stat['count']
        
        labels = [months_map[month] for month in range(1, 13)]
        data = [all_data[month] for month in range(1, 13)]
        
    else:  # hour
        # Consulta por hora del día
        stats = base_query.filter(
            ultima_lectura__year=selected_year,
            ultima_lectura__month=selected_month
        ).annotate(
            hour=ExtractHour('ultima_lectura')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('hour')
        
        all_data = {hour: 0 for hour in range(24)}
        for stat in stats:
            all_data[stat['hour']] = stat['count']
        
        labels = [f'{hour:02d}:00' for hour in range(24)]
        data = [all_data[hour] for hour in range(24)]
    
    return JsonResponse({
        'labels': labels,
        'data': data
    })
    
 
 
 
@login_required
@role_required(['porteria', 'administrador'])
def validar_qr_vehicular(request, encrypted_token):
    """
    Vista separada para validar QRs de visitantes vehiculares.
    Mantiene la lógica similar a validar_qr pero permite dos lecturas.
    """
    logger.info("Iniciando validación de QR vehicular")
    
    # Verificar si es una pre-carga de Safari/iOS
    is_ios_prefetch = (
        'purpose' in request.headers and 
        request.headers['purpose'] == 'prefetch'
    ) or (
        'Sec-Purpose' in request.headers and 
        request.headers['Sec-Purpose'] == 'prefetch'
    )

    if is_ios_prefetch:
        logger.info("Detectada pre-carga de iOS - ignorando validación")
        return HttpResponse(status=204)

    source = request.GET.get('source', '')
    if source != 'scan':
        logger.warning("Intento de acceso sin escaneo")
        return render(request, 'error_qr.html', {
            'mensaje': 'Acceso no autorizado. Escanea el QR desde la aplicación.'
        })

    try:
        # Desencriptar token
        decrypted_token = cipher.decrypt(encrypted_token.encode()).decode()
        if not decrypted_token.startswith("Kislev_"):
            logger.error("Token inválido: prefijo incorrecto")
            return render(request, 'error_qr.html', {'mensaje': 'Token no válido.'})

        original_token = decrypted_token[len("Kislev_"):]
        
        # Obtener visitante con bloqueo
        with transaction.atomic():
            visitante = get_object_or_404(
                VisitanteVehicular.objects.select_for_update(nowait=True),
                token=original_token
            )
            
            # Verificar estado directamente en la base de datos
            visitante.refresh_from_db()
            
            if not visitante.puede_leer():
                return render(request, 'qr_desactivado.html', {
                    'mensaje': 'Este código QR ya completó sus dos lecturas.',
                    'ultima_lectura': visitante.segunda_lectura or visitante.ultima_lectura
                })

            # Registrar la lectura
            lectura_exitosa = visitante.registrar_lectura()
            if not lectura_exitosa:
                return render(request, 'error_qr.html', {
                    'mensaje': 'Error al registrar la lectura del QR.'
                })

            # Determinar si es entrada o salida
            es_entrada = not visitante.segunda_lectura
            mensaje = 'Entrada registrada' if es_entrada else 'Salida registrada'

            # Enviar notificación por email
            try:
                email_subject = f"Registro vehicular - {mensaje}"
                email_body = f"""
                Hola,
                
                Tu visitante {visitante.nombre} ha registrado un movimiento en portería.
                Estado: {mensaje}
                Fecha y hora: {timezone.localtime(visitante.ultima_lectura).strftime('%Y-%m-%d %H:%M:%S')}
                Vehículo: {visitante.get_tipo_vehiculo_display()}
                Placa: {visitante.placa}
                Motivo de la visita: {visitante.motivo}
                
                Saludos,
                Kislev
                """
                
                email = EmailMessage(
                    email_subject,
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [visitante.email_creador],
                    headers={'X-Priority': '1'}
                )
                email.send(fail_silently=False)
                logger.info(f"Notificación enviada a {visitante.email_creador}")
            except Exception as e:
                logger.error(f"Error enviando notificación por email: {str(e)}")

            return render(request, 'validar_qr.html', {
                'visitante': visitante,
                'mensaje': mensaje,
                'es_vehicular': True,
                'es_entrada': es_entrada
            })

    except Exception as e:
        logger.error(f"Error procesando QR vehicular: {str(e)}")
        return render(request, 'error_qr.html', {
            'mensaje': f'Error al procesar el QR: {str(e)}'
        })
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
@login_required
def disponibilidad_carros(request):
    """Vista para mostrar solo la disponibilidad de carros"""
    conjunto_id = request.user.conjunto_id
    
    # Obtener o crear registro de parqueadero para el conjunto
    parqueadero, created = ParqueaderoCarro.objects.get_or_create(
        conjunto_id=conjunto_id,
        defaults={'total_espacios': 0}
    )
    
    # Obtener disponibilidad
    disponibilidad = ParqueaderoCarro.get_disponibilidad(conjunto_id)
    
    # Obtener vehículos activos
    vehiculos_activos = VisitanteVehicular.objects.filter(
        conjunto_id=conjunto_id,
        tipo_vehiculo='carro',
        ultima_lectura__isnull=False,
        segunda_lectura__isnull=True
    ).select_related('conjunto').order_by('-ultima_lectura')
    
    context = {
        'disponibilidad': disponibilidad,
        'vehiculos_activos': vehiculos_activos,
        'conjunto': request.user.conjunto,
    }
    
    return render(request, 'parking/disponibilidad_tipo.html', context)

@login_required
def disponibilidad_motos(request):
    """Vista para mostrar solo la disponibilidad de motos"""
    conjunto_id = request.user.conjunto_id

    # Obtener o crear registro de parqueadero para el conjunto
    parqueadero, created = ParqueaderoMoto.objects.get_or_create(
        conjunto_id=conjunto_id,
        defaults={'total_espacios': 0}
    )

    # Obtener disponibilidad
    disponibilidad = ParqueaderoMoto.get_disponibilidad(conjunto_id)

    # Obtener vehículos activos
    vehiculos_activos = VisitanteVehicular.objects.filter(
        conjunto_id=conjunto_id,
        tipo_vehiculo='moto',
        ultima_lectura__isnull=False,
        segunda_lectura__isnull=True
    ).select_related('conjunto').order_by('-ultima_lectura')

    context = {
        'disponibilidad': disponibilidad,
        'vehiculos_activos': vehiculos_activos,
        'conjunto': request.user.conjunto,
    }

    return render(request, 'parking/disponibilidad_tipo.html', context)


@login_required
@role_required(['administrador'])
def metricas_parqueadero(request, tipo):
    from django.db.models import Avg, F, ExpressionWrapper, DurationField
    from django.db.models.functions import TruncHour, TruncDate
    from django.utils import timezone as _tz
    import json

    if tipo not in ('carro', 'moto'):
        return redirect('parking')

    conjunto_id = request.user.conjunto_id
    now = _tz.localtime(_tz.now())
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hoy_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Disponibilidad actual
    if tipo == 'carro':
        disp = ParqueaderoCarro.get_disponibilidad(conjunto_id)
    else:
        disp = ParqueaderoMoto.get_disponibilidad(conjunto_id)

    base_qs = VisitanteVehicular.objects.filter(conjunto_id=conjunto_id, tipo_vehiculo=tipo)

    # KPIs
    ingresos_hoy = base_qs.filter(ultima_lectura__gte=hoy_inicio).count()
    ingresos_mes = base_qs.filter(ultima_lectura__gte=inicio_mes).count()
    salidas_hoy = base_qs.filter(segunda_lectura__gte=hoy_inicio).count()

    # Tiempo promedio de permanencia (solo los que ya salieron)
    completados = base_qs.filter(ultima_lectura__isnull=False, segunda_lectura__isnull=False)
    tiempo_promedio_min = None
    if completados.exists():
        duraciones = [
            (v.segunda_lectura - v.ultima_lectura).total_seconds() / 60
            for v in completados
            if v.segunda_lectura > v.ultima_lectura
        ]
        if duraciones:
            tiempo_promedio_min = round(sum(duraciones) / len(duraciones))

    # Vehículos actualmente dentro
    dentro = base_qs.filter(
        ultima_lectura__isnull=False,
        segunda_lectura__isnull=True
    ).order_by('-ultima_lectura')[:20]

    dentro_list = []
    for v in dentro:
        mins = int((now - _tz.localtime(v.ultima_lectura)).total_seconds() / 60)
        dentro_list.append({
            'placa': v.placa,
            'nombre': v.nombre,
            'entrada': _tz.localtime(v.ultima_lectura).strftime('%H:%M'),
            'tiempo': f'{mins // 60}h {mins % 60}m' if mins >= 60 else f'{mins}m',
        })

    # Horas pico del mes (ingresos por hora)
    horas_raw = (
        base_qs.filter(ultima_lectura__gte=inicio_mes)
        .annotate(hora=TruncHour('ultima_lectura'))
        .values('hora')
        .annotate(total=models.Count('id'))
        .order_by('hora')
    )
    horas_pico = [0] * 24
    for row in horas_raw:
        h = _tz.localtime(row['hora']).hour
        horas_pico[h] += row['total']

    # Top 10 placas del mes
    top_placas = (
        base_qs.filter(ultima_lectura__gte=inicio_mes)
        .values('placa', 'nombre')
        .annotate(total=models.Count('id'))
        .order_by('-total')[:10]
    )

    # Ingresos por día del mes (últimos 30 días)
    dias_raw = (
        base_qs.filter(ultima_lectura__gte=inicio_mes)
        .annotate(dia=TruncDate('ultima_lectura'))
        .values('dia')
        .annotate(total=models.Count('id'))
        .order_by('dia')
    )
    dias_labels = [row['dia'].strftime('%d/%m') for row in dias_raw]
    dias_data = [row['total'] for row in dias_raw]

    context = {
        'tipo': tipo,
        'tipo_label': 'Carros' if tipo == 'carro' else 'Motos',
        'disp': disp,
        'ingresos_hoy': ingresos_hoy,
        'ingresos_mes': ingresos_mes,
        'salidas_hoy': salidas_hoy,
        'tiempo_promedio_min': tiempo_promedio_min,
        'dentro_list': dentro_list,
        'horas_pico_json': json.dumps(horas_pico),
        'top_placas': list(top_placas),
        'dias_labels_json': json.dumps(dias_labels),
        'dias_data_json': json.dumps(dias_data),
        'now': now,
    }
    return render(request, 'parking/metricas_parqueadero.html', context)


@login_required
def historial_vehiculos(request, tipo_vehiculo):
    """Vista para mostrar el historial de movimientos de vehículos"""
    conjunto_id = request.user.conjunto_id
    
    # Obtener todos los movimientos del tipo de vehículo especificado
    movimientos = VisitanteVehicular.objects.filter(
        conjunto_id=conjunto_id,
        tipo_vehiculo=tipo_vehiculo,
        ultima_lectura__isnull=False
    ).select_related('conjunto').order_by('-ultima_lectura')
    
    context = {
        'movimientos': movimientos,
        'tipo_vehiculo': 'Carros' if tipo_vehiculo == 'carro' else 'Motos',
        'conjunto': request.user.conjunto
    }
    
    return render(request, 'parking/historial_vehiculos.html', context)



@login_required
def get_torres(request):
    """API para obtener las torres del conjunto del usuario logueado"""
    try:
        conjunto = request.user.conjunto
        
        # Obtener todas las torres activas del conjunto
        torres = Torre.objects.filter(
            conjunto=conjunto,
            activo=True
        ).values('id', 'nombre')
        
        return JsonResponse({
            'status': 'success',
            'torres': list(torres)
        })
    except Exception as e:
        logger.error(f"Error al obtener torres: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error al cargar las torres'
        }, status=500)

@login_required
def get_apartamentos(request, torre_id):
    """API para obtener los apartamentos de una torre específica"""
    try:
        # Verificar que la torre pertenece al conjunto del usuario
        torre = get_object_or_404(
            Torre, 
            id=torre_id, 
            conjunto=request.user.conjunto,
            activo=True
        )
        
        # Generar lista de apartamentos según la configuración de la torre
        apartamentos = torre.get_apartamentos()
        
        # También obtener los apartamentos que ya están ocupados
        ocupados = Usuario.objects.filter(
            torre=torre,
            is_active=True
        ).values_list('apartamento', flat=True)
        
        response = {
            'status': 'success',
            'apartamentos': apartamentos,
            'ocupados': list(ocupados),
        }
        # Si viene ?apto=XXX, devolver info del residente para el formulario de paquetes
        apto = request.GET.get('apto', '').strip()
        if apto:
            residente = Usuario.objects.filter(
                torre=torre, apartamento=apto, user_type='propietario', is_active=True
            ).first()
            response['residente'] = residente.nombre if residente else None
            response['telefono'] = residente.phone_number if residente else None
        return JsonResponse(response)
    except Exception as e:
        logger.error(f"Error al obtener apartamentos: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error al cargar los apartamentos'
        }, status=500)


# ─── REPORTE PDF ──────────────────────────────────────────────────────────────

@login_required
@role_required(['administrador'])
def reporte_pdf_mensual(request):
    """Genera un PDF con el resumen mensual del conjunto."""
    from weasyprint import HTML as WeasyHTML
    import calendar

    conjunto_id = request.user.conjunto_id
    mes = int(request.GET.get('mes', timezone.now().month))
    año = int(request.GET.get('año', timezone.now().year))
    mes_nombre = calendar.month_name[mes].capitalize()

    fecha_actual = timezone.now().date()
    primer_dia = fecha_actual.replace(day=1, month=mes, year=año)
    ultimo_dia = fecha_actual.replace(
        day=calendar.monthrange(año, mes)[1], month=mes, year=año
    )

    visitantes_mes = Visitante.objects.filter(
        conjunto_id=conjunto_id,
        fecha_generacion__date__gte=primer_dia,
        fecha_generacion__date__lte=ultimo_dia,
    )
    reservas_mes = Reserva.objects.filter(
        fecha__gte=primer_dia, fecha__lte=ultimo_dia
    ).select_related('sala')
    pagos_mes = Pago.objects.filter(
        cuota__conjunto_id=conjunto_id,
        fecha_pago__gte=primer_dia,
        fecha_pago__lte=ultimo_dia,
    ).select_related('propietario', 'cuota')
    recaudo = pagos_mes.aggregate(total=models.Sum('monto_pagado'))['total'] or 0

    html_str = render_to_string('finanzas/reporte_pdf.html', {
        'conjunto': request.user.conjunto,
        'mes_nombre': mes_nombre,
        'año': año,
        'fecha_generacion': timezone.now(),
        'visitantes_mes': visitantes_mes,
        'total_visitantes': visitantes_mes.count(),
        'ingresos_qr': visitantes_mes.exclude(ultima_lectura=None).count(),
        'reservas_mes': reservas_mes,
        'total_reservas': reservas_mes.count(),
        'pagos_mes': pagos_mes,
        'recaudo': recaudo,
    })

    pdf_file = WeasyHTML(string=html_str, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reporte_{mes_nombre}_{año}.pdf"'
    return response


# ─── MÓDULO FINANCIERO ────────────────────────────────────────────────────────

@login_required
@role_required(['administrador'])
def finanzas_admin(request):
    """Panel financiero del administrador: listado de cuotas y estado de pagos."""
    conjunto_id = request.user.conjunto_id
    cuotas = Cuota.objects.filter(conjunto_id=conjunto_id).prefetch_related('pagos__propietario')
    propietarios = Usuario.objects.filter(
        conjunto_id=conjunto_id, user_type='propietario', is_active=True
    ).select_related('torre')

    return render(request, 'finanzas/admin_cuotas.html', {
        'cuotas': cuotas,
        'propietarios': propietarios,
        'total_propietarios': propietarios.count(),
    })


@login_required
@role_required(['administrador'])
@require_POST
def crear_cuota(request):
    """Crea una nueva cuota para el conjunto."""
    try:
        nombre = sanitize_text(request.POST.get('nombre', ''))
        descripcion = sanitize_text(request.POST.get('descripcion', ''))
        monto = int(request.POST.get('monto', 0))
        periodicidad = request.POST.get('periodicidad', 'mensual')
        fecha_vencimiento = request.POST.get('fecha_vencimiento')

        if not nombre or monto <= 0 or not fecha_vencimiento:
            return JsonResponse({'status': 'error', 'message': 'Datos incompletos.'}, status=400)

        from datetime import date as date_type
        fecha = datetime.strptime(fecha_vencimiento, '%Y-%m-%d').date()

        cuota = Cuota.objects.create(
            conjunto_id=request.user.conjunto_id,
            nombre=nombre,
            descripcion=descripcion,
            monto=monto,
            periodicidad=periodicidad,
            fecha_vencimiento=fecha,
        )
        log_audit(request, 'reserva_creada', f"Cuota creada: {cuota.nombre} ${cuota.monto:,.0f}")
        return JsonResponse({'status': 'ok', 'message': 'Cuota creada exitosamente.', 'id': cuota.id})
    except (ValueError, TypeError) as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@role_required(['administrador'])
@require_POST
def registrar_pago(request, cuota_id):
    """Registra el pago de un propietario para una cuota."""
    cuota = get_object_or_404(Cuota, id=cuota_id, conjunto_id=request.user.conjunto_id)
    try:
        propietario_id = int(request.POST.get('propietario_id'))
        monto_pagado = int(request.POST.get('monto_pagado', cuota.monto))
        metodo = request.POST.get('metodo', 'transferencia')
        comprobante = sanitize_text(request.POST.get('comprobante', ''))
        fecha_pago = datetime.strptime(request.POST.get('fecha_pago'), '%Y-%m-%d').date()

        propietario = get_object_or_404(
            Usuario, id=propietario_id, conjunto_id=request.user.conjunto_id, user_type='propietario'
        )

        pago, created = Pago.objects.update_or_create(
            cuota=cuota,
            propietario=propietario,
            defaults={
                'monto_pagado': monto_pagado,
                'metodo': metodo,
                'comprobante': comprobante,
                'fecha_pago': fecha_pago,
                'registrado_por': request.user,
            }
        )
        accion = 'Pago registrado' if created else 'Pago actualizado'
        log_audit(request, 'reserva_creada',
                  f"{accion}: {propietario.nombre} — {cuota.nombre} ${monto_pagado:,.0f}")
        return JsonResponse({'status': 'ok', 'message': f'{accion} exitosamente.'})
    except (ValueError, TypeError) as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@role_required(['propietario'])
def estado_cuenta(request):
    """Vista del propietario: su estado de cuenta por cuota."""
    conjunto_id = request.user.conjunto_id
    cuotas = Cuota.objects.filter(conjunto_id=conjunto_id).prefetch_related(
        models.Prefetch('pagos', queryset=Pago.objects.filter(propietario=request.user))
    )

    resumen = []
    total_deuda = 0
    for cuota in cuotas:
        pago = cuota.pagos.first()
        pendiente = cuota.monto - (pago.monto_pagado if pago else 0)
        if pendiente > 0:
            total_deuda += pendiente
        resumen.append({
            'cuota': cuota,
            'pago': pago,
            'pendiente': max(pendiente, 0),
        })

    return render(request, 'finanzas/estado_cuenta.html', {
        'resumen': resumen,
        'total_deuda': total_deuda,
    })

# ─────────────────────────────────────────────
#  NOVEDADES
# ─────────────────────────────────────────────

@login_required
def lista_novedades(request):
    novedades = Novedad.objects.filter(
        conjunto=request.user.conjunto, activa=True
    ).prefetch_related('archivos', 'comentarios')
    return render(request, 'novedades/lista.html', {'novedades': novedades})


@login_required
def detalle_novedad(request, pk):
    novedad = get_object_or_404(Novedad, pk=pk, conjunto=request.user.conjunto, activa=True)
    comentarios = novedad.comentarios.select_related('usuario').all()
    user_liked = novedad.likes.filter(usuario=request.user).exists()
    like_count = novedad.likes.count()
    # Marcar como vista
    NovedadVista.objects.get_or_create(novedad=novedad, usuario=request.user)
    return render(request, 'novedades/detalle.html', {
        'novedad': novedad,
        'comentarios': comentarios,
        'user_liked': user_liked,
        'like_count': like_count,
    })


@login_required
@require_POST
def agregar_comentario(request, pk):
    novedad = get_object_or_404(Novedad, pk=pk, conjunto=request.user.conjunto, activa=True)
    texto = request.POST.get('texto', '').strip()
    if texto:
        ComentarioNovedad.objects.create(novedad=novedad, usuario=request.user, texto=texto)
    return redirect('detalle_novedad', pk=pk)


@login_required
def crear_novedad(request):
    if request.user.user_type != 'administrador':
        return redirect('lista_novedades')

    if request.method == 'POST':
        titulo   = sanitize_text(request.POST.get('titulo', '').strip())
        contenido = request.POST.get('contenido', '').strip()
        imagen   = request.FILES.get('imagen')
        archivos = request.FILES.getlist('archivos')

        if not titulo or not contenido:
            messages.error(request, 'El título y el contenido son obligatorios.')
            return render(request, 'novedades/crear.html')

        novedad = Novedad.objects.create(
            conjunto=request.user.conjunto,
            autor=request.user,
            titulo=titulo,
            contenido=contenido,
            imagen=imagen,
        )

        for f in archivos:
            ArchivoNovedad.objects.create(
                novedad=novedad,
                archivo=f,
                nombre_original=f.name,
            )

        _enviar_email_novedad(novedad, request)
        log_audit(request, 'visitante_creado', f'Novedad publicada: {titulo}')
        messages.success(request, 'Novedad publicada y notificación enviada.')
        return redirect('detalle_novedad', pk=novedad.pk)

    return render(request, 'novedades/crear.html')


@login_required
def eliminar_novedad(request, pk):
    if request.user.user_type != 'administrador':
        return redirect('lista_novedades')
    novedad = get_object_or_404(Novedad, pk=pk, conjunto=request.user.conjunto)
    novedad.activa = False
    novedad.save()
    messages.success(request, 'Novedad eliminada.')
    return redirect('lista_novedades')


def _enviar_email_novedad(novedad, request):
    """Envía email a todos los usuarios activos del conjunto al publicar una novedad."""
    try:
        usuarios = Usuario.objects.filter(
            conjunto=novedad.conjunto, is_active=True
        ).exclude(pk=novedad.autor_id).values_list('email', flat=True)
        emails = [e for e in usuarios if e]
        if not emails:
            return

        url = request.build_absolute_uri(f'/novedades/{novedad.pk}/')
        subject = f'[{novedad.conjunto.nombre}] Nueva novedad: {novedad.titulo}'
        plain = f'{novedad.titulo}\n\n{novedad.contenido}\n\nVer novedad: {url}'
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
          <div style="background:linear-gradient(135deg,#7f00ff,#e100ff);padding:30px;border-radius:12px 12px 0 0;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:22px;">📢 {novedad.titulo}</h1>
            <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;">{novedad.conjunto.nombre}</p>
          </div>
          <div style="background:#fff;padding:30px;border-radius:0 0 12px 12px;border:1px solid #eee;">
            <p style="color:#333;font-size:15px;line-height:1.6;">{novedad.contenido[:400]}{'...' if len(novedad.contenido)>400 else ''}</p>
            <div style="text-align:center;margin:24px 0;">
              <a href="{url}" style="background:linear-gradient(135deg,#7f00ff,#e100ff);color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;">Ver novedad completa</a>
            </div>
            <p style="color:#999;font-size:12px;text-align:center;">Kislev — Sistema de gestión residencial</p>
          </div>
        </div>"""

        for email in emails:
            msg = EmailMultiAlternatives(subject, plain, settings.DEFAULT_FROM_EMAIL, [email])
            msg.attach_alternative(html, 'text/html')
            msg.send(fail_silently=True)
    except Exception as e:
        logger.error(f'Error enviando emails novedad: {e}')


@login_required
@require_POST
def toggle_like(request, pk):
    novedad = get_object_or_404(Novedad, pk=pk, conjunto=request.user.conjunto, activa=True)
    like, created = LikeNovedad.objects.get_or_create(novedad=novedad, usuario=request.user)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'total': novedad.likes.count()})


@login_required
def metricas_novedades(request):
    if request.user.user_type != 'administrador':
        return redirect('lista_novedades')

    from django.db.models import Count, Avg
    from django.utils import timezone
    import datetime

    conjunto = request.user.conjunto

    # Filtros
    fecha_desde = request.GET.get('desde')
    fecha_hasta = request.GET.get('hasta')

    qs = Novedad.objects.filter(conjunto=conjunto, activa=True)
    if fecha_desde:
        try:
            qs = qs.filter(created_at__date__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(created_at__date__lte=fecha_hasta)
        except Exception:
            pass

    novedades = qs.annotate(
        n_likes=Count('likes', distinct=True),
        n_comentarios=Count('comentarios', distinct=True),
    ).order_by('-created_at')

    total_novedades = novedades.count()
    total_likes     = sum(n.n_likes for n in novedades)
    total_comentarios = sum(n.n_comentarios for n in novedades)
    top_like = max(novedades, key=lambda n: n.n_likes, default=None)
    top_comment = max(novedades, key=lambda n: n.n_comentarios, default=None)
    promedio_likes = round(total_likes / total_novedades, 1) if total_novedades else 0
    promedio_comentarios = round(total_comentarios / total_novedades, 1) if total_novedades else 0

    # Engagement: (likes + comentarios) por novedad en promedio
    engagement = round((total_likes + total_comentarios) / total_novedades, 1) if total_novedades else 0

    context = {
        'novedades': novedades,
        'total_novedades': total_novedades,
        'total_likes': total_likes,
        'total_comentarios': total_comentarios,
        'top_like': top_like,
        'top_comment': top_comment,
        'promedio_likes': promedio_likes,
        'promedio_comentarios': promedio_comentarios,
        'engagement': engagement,
        'fecha_desde': fecha_desde or '',
        'fecha_hasta': fecha_hasta or '',
    }
    return render(request, 'novedades/metricas.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO DE PAQUETES / MENSAJERÍA
# ─────────────────────────────────────────────────────────────────────────────
import random as _random
from .utils import send_whatsapp, mensaje_paquete


def _generar_codigo_paquete():
    """Genera un código numérico de 6 dígitos único entre paquetes pendientes."""
    for _ in range(20):
        codigo = str(_random.randint(100000, 999999))
        if not Paquete.objects.filter(codigo=codigo, estado='pendiente').exists():
            return codigo
    return str(_random.randint(100000, 999999))


@login_required
def registrar_paquete(request):
    if request.user.user_type not in ('administrador', 'porteria'):
        messages.error(request, 'Acceso restringido')
        return redirect('lista_salas')

    conjunto = request.user.conjunto
    torres = Torre.objects.filter(conjunto=conjunto, activo=True)

    if request.method == 'POST':
        torre_id = request.POST.get('torre')
        apartamento = request.POST.get('apartamento', '').strip()
        empresa = request.POST.get('empresa', '')
        descripcion = request.POST.get('descripcion', '').strip()

        try:
            torre = get_object_or_404(Torre, id=torre_id, conjunto=conjunto)

            # Buscar propietario del apto para obtener nombre y teléfono
            residente = Usuario.objects.filter(
                conjunto=conjunto, torre=torre, apartamento=apartamento, user_type='propietario'
            ).first()
            destinatario_nombre = residente.nombre if residente else f'Residente Apto {apartamento}'
            destinatario_telefono = (residente.phone_number or '') if residente else ''

            codigo = _generar_codigo_paquete()
            paquete = Paquete.objects.create(
                conjunto=conjunto,
                torre=torre,
                apartamento=apartamento,
                empresa=empresa,
                descripcion=descripcion,
                codigo=codigo,
                registrado_por=request.user,
                destinatario_nombre=destinatario_nombre,
                destinatario_telefono=destinatario_telefono,
            )

            # Enviar WhatsApp si hay teléfono
            wa_enviado = False
            if destinatario_telefono:
                from django.utils import timezone as _tz
                now = _tz.localtime(_tz.now())
                msg = mensaje_paquete(
                    nombre=destinatario_nombre,
                    conjunto=conjunto.nombre,
                    torre=torre.nombre,
                    apartamento=apartamento,
                    empresa=dict(Paquete.EMPRESAS).get(empresa, empresa),
                    fecha=now.strftime('%d/%m/%Y'),
                    hora=now.strftime('%H:%M'),
                    codigo=codigo,
                )
                wa_enviado = send_whatsapp(destinatario_telefono, msg)
                paquete.whatsapp_enviado = wa_enviado
                paquete.save(update_fields=['whatsapp_enviado'])

            log_audit(request, 'paquete_registrado',
                      f"Torre {torre.nombre} Apto {apartamento} | {empresa} | código {codigo}")

            if wa_enviado:
                messages.success(request, f'Paquete registrado ✓ · Código: {codigo} · WhatsApp enviado a {destinatario_nombre}')
            elif destinatario_telefono:
                messages.success(request, f'Paquete registrado ✓ · Código: {codigo} · (WhatsApp no disponible — teléfono: {destinatario_telefono})')
            else:
                messages.success(request, f'Paquete registrado ✓ · Código: {codigo} · El residente no tiene teléfono registrado')

            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f'Error al registrar: {e}')

    return render(request, 'paquetes/registrar_paquete.html', {
        'torres': torres,
        'empresas': Paquete.EMPRESAS,
    })


@login_required
def entregar_paquete(request):
    """API: verifica código y entrega paquete. POST JSON → {ok, mensaje, paquete}"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'mensaje': 'Método no permitido'}, status=405)
    if request.user.user_type not in ('administrador', 'porteria'):
        return JsonResponse({'ok': False, 'mensaje': 'Acceso restringido'}, status=403)

    try:
        data = json.loads(request.body)
        codigo = data.get('codigo', '').strip()
    except Exception:
        codigo = request.POST.get('codigo', '').strip()

    if not codigo:
        return JsonResponse({'ok': False, 'mensaje': 'Ingresa el código'})

    paquete = Paquete.objects.filter(
        codigo=codigo, estado='pendiente', conjunto=request.user.conjunto
    ).select_related('torre').first()

    if not paquete:
        return JsonResponse({'ok': False, 'mensaje': 'Código incorrecto o paquete ya entregado'})

    paquete.estado = 'entregado'
    paquete.fecha_entrega = timezone.now()
    paquete.entregado_por = request.user
    paquete.save(update_fields=['estado', 'fecha_entrega', 'entregado_por'])
    log_audit(request, 'paquete_entregado',
              f"Código {codigo} | Torre {paquete.torre.nombre} Apto {paquete.apartamento}")

    return JsonResponse({
        'ok': True,
        'mensaje': f'¡Entregado! · {paquete.destinatario_nombre} · Torre {paquete.torre.nombre} Apto {paquete.apartamento}',
        'paquete': {
            'codigo': paquete.codigo,
            'torre': paquete.torre.nombre,
            'apartamento': paquete.apartamento,
            'empresa': paquete.empresa_display,
            'destinatario': paquete.destinatario_nombre,
        }
    })


@login_required
def dashboard_kpi_paquetes(request):
    """Endpoint AJAX para refrescar KPIs de paquetes en el dashboard."""
    conjunto_id = request.user.conjunto_id
    fecha_actual = timezone.localtime(timezone.now()).date()
    data = {
        'pendientes': Paquete.objects.filter(conjunto_id=conjunto_id, estado='pendiente').count(),
        'hoy_recibidos': Paquete.objects.filter(conjunto_id=conjunto_id, fecha_registro__date=fecha_actual).count(),
        'hoy_entregados': Paquete.objects.filter(conjunto_id=conjunto_id, fecha_entrega__date=fecha_actual).count(),
    }
    return JsonResponse(data)


@login_required
def lista_paquetes(request):
    conjunto = request.user.conjunto
    torres = Torre.objects.filter(conjunto=conjunto, activo=True)

    qs = Paquete.objects.filter(conjunto=conjunto).select_related('torre', 'registrado_por', 'entregado_por')

    # Filtros
    torre_id = request.GET.get('torre', '')
    apartamento = request.GET.get('apto', '').strip()
    estado = request.GET.get('estado', '')
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')

    if torre_id:
        qs = qs.filter(torre_id=torre_id)
    if apartamento:
        qs = qs.filter(apartamento=apartamento)
    if estado:
        qs = qs.filter(estado=estado)
    if fecha_desde:
        qs = qs.filter(fecha_registro__date__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha_registro__date__lte=fecha_hasta)

    qs = qs.order_by('-fecha_registro')[:200]

    return render(request, 'paquetes/lista_paquetes.html', {
        'paquetes': qs,
        'torres': torres,
        'filtros': {
            'torre_id': torre_id,
            'apto': apartamento,
            'estado': estado,
            'desde': fecha_desde,
            'hasta': fecha_hasta,
        },
    })


@login_required
def metricas_paquetes(request):
    if request.user.user_type != 'administrador':
        messages.error(request, 'Acceso restringido')
        return redirect('lista_paquetes')

    conjunto = request.user.conjunto
    hoy = timezone.now().date()
    mes_inicio = hoy.replace(day=1)

    qs = Paquete.objects.filter(conjunto=conjunto)
    total = qs.count()
    pendientes = qs.filter(estado='pendiente').count()
    entregados = qs.filter(estado='entregado').count()
    hoy_registrados = qs.filter(fecha_registro__date=hoy).count()
    hoy_entregados = qs.filter(fecha_entrega__date=hoy).count()
    mes_registrados = qs.filter(fecha_registro__date__gte=mes_inicio).count()

    por_empresa = list(
        qs.values('empresa').annotate(total=Count('id')).order_by('-total')[:8]
    )
    for e in por_empresa:
        e['empresa_display'] = dict(Paquete.EMPRESAS).get(e['empresa'], e['empresa'])

    por_torre = list(
        qs.filter(estado='pendiente').values('torre__nombre').annotate(total=Count('id')).order_by('-total')
    )

    ultimos = qs.select_related('torre').order_by('-fecha_registro')[:20]

    return render(request, 'paquetes/metricas_paquetes.html', {
        'total': total,
        'pendientes': pendientes,
        'entregados': entregados,
        'hoy_registrados': hoy_registrados,
        'hoy_entregados': hoy_entregados,
        'mes_registrados': mes_registrados,
        'por_empresa': por_empresa,
        'por_torre': por_torre,
        'ultimos': ultimos,
        'conjunto': conjunto,
    })


@login_required
@role_required(['propietario'])
def regenerar_qr_visitante(request, visitante_id):
    """Crea un nuevo QR para un visitante existente sin re-llenar el formulario."""
    visitante_original = get_object_or_404(
        Visitante,
        id=visitante_id,
        conjunto_id=request.user.conjunto_id,
        numper=request.user.apartamento,
    )

    uuid_token = str(uuid.uuid4())
    nuevo = Visitante.objects.create(
        email=visitante_original.email,
        nombre=visitante_original.nombre,
        celular=visitante_original.celular,
        cedula=visitante_original.cedula,
        motivo=visitante_original.motivo,
        email_creador=request.user.email,
        nombre_log=visitante_original.nombre_log,
        token=uuid_token,
        fecha_generacion=timezone.now(),
        numper=visitante_original.numper,
        conjunto_id=visitante_original.conjunto_id,
        ultima_lectura=None,
    )

    raw_token = f"Kislev_peatonal_{uuid_token}"
    encrypted_token = cipher.encrypt(raw_token.encode()).decode()
    base_url = f"https://{request.get_host()}" if 'railway.app' in request.get_host() else request.build_absolute_uri('/').rstrip('/')
    enlace_qr = f"{base_url}{reverse('validar_qr', args=[encrypted_token])}"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(enlace_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)

    try:
        email_message = EmailMessage(
            "Tu nuevo Código QR de Visitante",
            f"Hola {nuevo.nombre},\n\nAdjunto encontrarás tu nuevo código QR para la visita.",
            settings.DEFAULT_FROM_EMAIL,
            [nuevo.email],
        )
        email_message.attach(f'qr_{nuevo.id}.png', qr_buffer.getvalue(), 'image/png')
        email_message.send()
    except Exception as e:
        logger.error(f"Error enviando email QR regenerado: {e}")

    log_audit(request, 'qr_regenerado', f"Visitante original: {visitante_original.id} → nuevo: {nuevo.id}")
    email_b64 = base64.urlsafe_b64encode(nuevo.email.encode()).decode()
    return redirect('valqr', email_b64=email_b64)
