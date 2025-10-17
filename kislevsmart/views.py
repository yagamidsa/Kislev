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
from .utils import role_required
from django.db.models import Count, F
from django.db.models.functions import ExtractMonth, ExtractWeekDay, ExtractHour
import json
from accounts.models import Usuario, ConjuntoResidencial, Torre
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, From, To, Subject, PlainTextContent, 
    HtmlContent, Header, Category, CustomArg
)
from django.views.decorators.http import require_http_methods
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from django.conf import settings
from django.views.generic import ListView
from .models import Sala, Reserva
from sendgrid.helpers.mail import Mail, To, Email, Content, Attachment, FileContent, FileName, FileType, Disposition
import logging
from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import HttpResponse
from django.views.decorators.vary import vary_on_headers
from .models import VisitanteVehicular
from .models import ParqueaderoCarro, ParqueaderoMoto



def sanitize_text(text):
    """
    Limpia el texto de caracteres inválidos para UTF-8 de forma más agresiva
    """
    if not text:
        return ""
    
    try:
        text = str(text)
        # Método 1: Codificar y decodificar ignorando errores
        text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        
        # Método 2: Remover explícitamente surrogates
        text = text.encode('utf-16', 'surrogatepass').decode('utf-16')
        text = text.encode('utf-8', errors='ignore').decode('utf-8')
        
        # Remover caracteres de control excepto saltos de línea
        text = ''.join(char for char in text if char == '\n' or char == '\r' or char == '\t' or not (0 <= ord(char) < 32))
        
        return text.strip()
    except Exception as e:
        logger.error(f"Error en sanitize_text: {e}")
        # Fallback: remover todo lo que no sea ASCII básico extendido
        return ''.join(char for char in str(text) if ord(char) < 128 or 128 <= ord(char) < 256)


# Configurar logger
logger = logging.getLogger(__name__)


#salas
class SalaListView(ListView):
    model = Sala
    template_name = 'salas/lista_salas.html'
    context_object_name = 'salas'

    def get_queryset(self):
        return Sala.objects.filter(estado=True)

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
    """
    API endpoint para obtener los horarios disponibles de un día específico
    """
    sala = get_object_or_404(Sala, id=sala_id)
    try:
        fecha_consulta = datetime.strptime(fecha, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)
    
    # Definir horarios de operación
    HORARIOS_OPERACION = [
        ('08:00', '09:00'),
        ('09:00', '10:00'),
        ('10:00', '11:00'),
        ('11:00', '12:00'),
        ('12:00', '13:00'),
        ('13:00', '14:00'),
        ('14:00', '15:00'),
        ('15:00', '16:00'),
        ('16:00', '17:00'),
        ('17:00', '18:00'),
        ('18:00', '19:00'),
        ('19:00', '20:00'),
        ('20:00', '21:00'),
        ('21:00', '22:00'),
    ]
    
    # Obtener todas las reservas del día
    reservas_dia = Reserva.objects.filter(
        sala=sala,
        fecha=fecha_consulta
    ).order_by('hora_inicio')

    # Convertir las reservas a rangos de hora para fácil comparación
    slots_ocupados = [(reserva.hora_inicio.strftime('%H:%M'), 
                       reserva.hora_fin.strftime('%H:%M')) 
                       for reserva in reservas_dia]

    # Encontrar slots disponibles
    slots_disponibles = []
    for inicio, fin in HORARIOS_OPERACION:
        slot_disponible = True
        for ocupado_inicio, ocupado_fin in slots_ocupados:
            # Verificar si hay solapamiento
            if not (fin <= ocupado_inicio or inicio >= ocupado_fin):
                slot_disponible = False
                break
        
        if slot_disponible:
            slots_disponibles.append({
                'inicio': inicio,
                'fin': fin
            })

    # Solo validar fechas pasadas, permitir fechas futuras
    if fecha_consulta < datetime.now().date():
        slots_disponibles = []
    
    # Si es el día actual, solo mostrar horarios futuros
    elif fecha_consulta == datetime.now().date():
        hora_actual = datetime.now().time()
        slots_disponibles = [
            slot for slot in slots_disponibles 
            if datetime.strptime(slot['inicio'], '%H:%M').time() > hora_actual
        ]

    return JsonResponse({
        'fecha': fecha,
        'slots_disponibles': slots_disponibles
    })

@login_required
def reservar_sala(request, sala_id):
    sala = get_object_or_404(Sala, id=sala_id)
    fecha = request.GET.get('fecha')
    hora_inicio = request.GET.get('hora_inicio')
    
    if request.method == 'POST':
        fecha = request.POST.get('fecha')
        hora_inicio = request.POST.get('hora_inicio')
        hora_fin = request.POST.get('hora_fin')
        notas = request.POST.get('notas', '')

        try:
            # Validar fecha y horas
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            hora_inicio_obj = datetime.strptime(hora_inicio, '%H:%M').time()
            hora_fin_obj = datetime.strptime(hora_fin, '%H:%M').time()

            # Validar que la fecha no sea en el pasado
            if fecha_obj < datetime.now().date():
                raise ValueError('No se pueden hacer reservas en fechas pasadas')

            # Validar horario de operación (8:00 AM a 10:00 PM)
            if hora_inicio_obj < datetime.strptime('08:00', '%H:%M').time() or \
               hora_fin_obj > datetime.strptime('22:00', '%H:%M').time():
                raise ValueError('El horario de reserva debe estar entre 8:00 AM y 10:00 PM')

            # Validar que hora_fin sea después de hora_inicio
            if hora_fin_obj <= hora_inicio_obj:
                raise ValueError('La hora de finalización debe ser posterior a la hora de inicio')

            # Verificar disponibilidad
            reservas_existentes = Reserva.objects.filter(
                sala=sala,
                fecha=fecha_obj,
                hora_inicio__lt=hora_fin_obj,
                hora_fin__gt=hora_inicio_obj
            )

            if reservas_existentes.exists():
                raise ValueError('Ya existe una reserva para este horario')

            # Crear la reserva
            Reserva.objects.create(
                sala=sala,
                fecha=fecha_obj,
                hora_inicio=hora_inicio_obj,
                hora_fin=hora_fin_obj,
                notas=notas
            )

            messages.success(request, 'Reserva creada exitosamente')
            
            # En lugar de redireccionar, renderizamos la misma página
            return render(request, 'salas/reservar.html', {
                'sala': sala,
                'fecha_seleccionada': fecha,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'notas': notas,
                'reserva_exitosa': True
            })

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, 'Error al crear la reserva')

    # Para GET request o si hay errores en POST
    return render(request, 'salas/reservar.html', {
        'sala': sala,
        'fecha_seleccionada': fecha,
        'hora_inicio': hora_inicio
    })

@login_required
def mis_reservas(request):
    reservas = Reserva.objects.filter(
        fecha__gte=datetime.now().date()
    ).order_by('fecha', 'hora_inicio')
    return render(request, 'salas/mis_reservas.html', {'reservas': reservas})

@login_required
def cancelar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    if request.method == 'POST':
        sala_id = reserva.sala.id
        reserva.delete()
        messages.success(request, 'Reserva cancelada exitosamente')
        return redirect('mis_reservas')
        
    return render(request, 'salas/confirmar_cancelacion.html', {'reserva': reserva})









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

        # 4. Inicializar SendGrid
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        
        # 5. Procesar archivos adjuntos si existen
        attachments = []
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
                encoded_file = base64.b64encode(archivo_contenido).decode()
                
                # Sanitizar nombre del archivo
                archivo_nombre_limpio = sanitize_text(archivo.name)
                
                attachment = Attachment()
                attachment.file_content = FileContent(encoded_file)
                attachment.file_name = FileName(archivo_nombre_limpio)
                attachment.file_type = FileType(archivo.content_type)
                attachment.disposition = Disposition('attachment')
                attachments.append(attachment)
                
                logger.info(f"Archivo adjunto procesado: {archivo_nombre_limpio} ({archivo.size/(1024*1024):.2f}MB)")
            except Exception as e:
                logger.error(f"Error procesando archivo {archivo.name}: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error procesando el archivo {archivo.name}: {str(e)}'
                })

        # 6. Preparar envío por lotes
        BATCH_SIZE = 500
        total_enviados = 0
        propietarios_list = list(propietarios)
        
        total_lotes = (len(propietarios_list) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(f"Iniciando envío a {total_propietarios} propietarios en {total_lotes} lotes con {len(attachments)} archivos adjuntos")
        
        # 7. Procesar cada lote
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
            plain_content = sanitize_text(f"""
Estimado/a {nombre_limpio},

{mensaje_usuario.replace('<br>', '\n')}

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
                # Sanitizar el HTML renderizado también
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

            # Crear mensaje de correo con configuraciones avanzadas
            message = Mail(
                from_email=From(
                    email=sanitize_text(settings.DEFAULT_FROM_EMAIL),
                    name=sanitize_text("Administración Conjunto Residencial")
                ),
                to_emails=To(
                    email=email_limpio,
                    name=nombre_limpio
                ),
                subject=Subject(sanitize_text('Notificación General')),
                plain_text_content=PlainTextContent(plain_content),
                html_content=HtmlContent(html_content)
            )

            # Añadir headers
            message.header = Header("List-Unsubscribe", f"<mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>")
            message.header = Header("Precedence", "bulk")
            message.category = Category("notificaciones_generales")
            message.reply_to = sanitize_text(settings.DEFAULT_FROM_EMAIL)

            # Agregar destinatarios BCC - SANITIZADOS
            for prop in other_props:
                try:
                    email_bcc_limpio = sanitize_text(prop['email'])
                    message.add_bcc(email_bcc_limpio)
                except Exception as e:
                    logger.warning(f"Error agregando BCC {prop.get('email', 'unknown')}: {e}")
                    continue

            # Agregar archivos adjuntos
            for attachment in attachments:
                message.add_attachment(attachment)

            # 8. Enviar lote
            try:
                response = sg.send(message)
                if response.status_code in [200, 201, 202]:
                    total_enviados += len(batch)
                    logger.info(f"Lote {batch_num}/{total_lotes} enviado: {len(batch)} destinatarios. Total: {total_enviados}/{total_propietarios}")
                else:
                    logger.warning(f"Respuesta inesperada en lote {batch_num}: {response.status_code}")
                    logger.warning(f"Detalles: {response.body}")
            except Exception as e:
                logger.error(f"Error enviando lote {batch_num}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                continue

        # 9. Retornar resultado
        if total_enviados > 0:
            success_message = f"Se enviaron {total_enviados} de {total_propietarios} notificaciones"
            
            if attachments:
                archivo_texto = "archivo" if len(attachments) == 1 else "archivos"
                success_message += f" con {len(attachments)} {archivo_texto} adjuntos ({round(total_size/(1024*1024), 2)}MB)"
            
            logger.info(success_message)
            
            return JsonResponse({
                'status': 'success',
                'enviados': total_enviados,
                'total': total_propietarios,
                'files_attached': len(attachments),
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
        archivos = []
        for file in request.FILES.getlist('files[]'):
            # Verificar tamaño
            if file.size > 10 * 1024 * 1024:  # 10MB
                return JsonResponse({
                    'status': 'error',
                    'message': f'El archivo {file.name} supera el límite de 10MB'
                }, status=400)
            
            # Guardar temporalmente para procesar
            archivo_contenido = file.read()
            encoded_file = base64.b64encode(archivo_contenido).decode()
            
            attachment = Attachment()
            attachment.file_content = FileContent(encoded_file)
            attachment.file_name = FileName(file.name)
            attachment.file_type = FileType(file.content_type)
            attachment.disposition = Disposition('attachment')
            archivos.append(attachment)
            
            logger.info(f"Archivo adjunto procesado: {file.name} ({file.size/(1024*1024):.2f}MB)")
        
        # Inicializar Sendgrid
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        
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
                plain_content = f"""
                Estimado/a {propietario.nombre},
                
                {mensaje.replace('<br>', '\n')}
                
                Esta notificación es exclusiva para su apartamento: {propietario.get_ubicacion_completa()}
                
                Atentamente,
                Administración {request.user.conjunto.nombre}
                
                ---------------------------------------------
                {request.user.conjunto.nombre}
                Teléfono: {request.user.conjunto.telefono or "(No disponible)"}
                Email: {request.user.conjunto.email_contacto or "(No disponible)"}
                """
                
                # Crear mensaje de correo
                message = Mail(
                    from_email=From(
                        email=settings.DEFAULT_FROM_EMAIL,
                        name=f"Administración {request.user.conjunto.nombre}"
                    ),
                    to_emails=To(
                        email=propietario.email,
                        name=propietario.nombre
                    ),
                    subject=Subject('Notificación Individual para su Apartamento'),
                    plain_text_content=PlainTextContent(plain_content),
                    html_content=HtmlContent(html_content)
                )
                
                # Añadir metadatos
                message.header = Header("List-Unsubscribe", f"<mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>")
                message.header = Header("Precedence", "bulk")
                message.header = Header("X-Priority", "1")
                message.header = Header("Importance", "High")
                message.category = Category("notificaciones_individuales")
                message.custom_arg = CustomArg("type", "individual_notification")
                message.reply_to = settings.DEFAULT_FROM_EMAIL
                
                # Agregar archivos adjuntos
                for attachment in archivos:
                    message.add_attachment(attachment)
                
                # Enviar correo
                response = sg.send(message)
                if response.status_code in [200, 201, 202]:
                    enviados += 1
                    logger.info(f"Notificación individual enviada a {propietario.email}")
                else:
                    logger.warning(f"Error al enviar notificación a {propietario.email}: Status {response.status_code}")
                
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
    Versión mejorada que utiliza la nueva plantilla HTML unificada.
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

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        successful_sends = 0
        failed_sends = 0
        errors = []

        # Dividir en lotes
        BATCH_SIZE = 500
        DELAY_BETWEEN_BATCHES = 2  # Segundos entre lotes
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
                    # Acceder usando la notación de diccionario
                    email = propietario['email']
                    nombre = propietario['nombre']
                    
                    # Preparar contexto para la plantilla
                    context = {
                        'nombre': nombre,
                        'service_type': service_type,
                        'fecha': datetime.now().strftime('%d/%m/%Y'),
                        'conjunto': conjunto_actual  # Usar el conjunto del usuario actual
                    }
                    
                    # Crear contenido HTML utilizando la plantilla
                    try:
                        html_content = render_to_string('emails/service_notification.html', context)
                        logger.debug(f"Plantilla HTML renderizada correctamente para {email}")
                    except Exception as e:
                        logger.warning(f"Error al renderizar plantilla: {str(e)}. Usando plantilla alternativa.")
                        # Plantilla alternativa simple en caso de error
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

                    # Crear mensaje con configuraciones anti-spam
                    message = Mail(
                        from_email=From(
                            email=settings.DEFAULT_FROM_EMAIL,
                            name="Administración Conjunto Residencial"
                        ),
                        to_emails=To(
                            email=email,
                            name=nombre
                        ),
                        subject=Subject(f'Notificación: Su factura de {service_type} está disponible'),
                        plain_text_content=PlainTextContent(plain_content),
                        html_content=HtmlContent(html_content)
                    )

                    # Añadir headers anti-spam y metadatos
                    message.header = Header("List-Unsubscribe", f"<mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>")
                    message.header = Header("Precedence", "bulk")
                    message.header = Header("X-Auto-Response-Suppress", "OOF, AutoReply")
                    message.header = Header("X-Priority", "1")
                    message.header = Header("Importance", "High")
                    message.category = Category("notificaciones_servicios")
                    message.custom_arg = CustomArg("type", "service_notification")
                    message.custom_arg = CustomArg("service", service_type)
                    message.reply_to = settings.DEFAULT_FROM_EMAIL

                    # Enviar email y verificar respuesta
                    response = sg.send(message)
                    
                    if response.status_code in [200, 201, 202]:
                        batch_successful += 1
                        successful_sends += 1
                        logger.debug(f"Email enviado exitosamente a {email}")
                    else:
                        batch_failed += 1
                        failed_sends += 1
                        errors.append({
                            'email': email,
                            'error': f"Status code {response.status_code}",
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                        logger.warning(f"Error al enviar email a {email}: Status code {response.status_code}")

                except Exception as e:
                    # Intentar obtener el email para el log de error
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

            # Esperar entre lotes para no sobrecargar la API
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
        
        # Incluir algunos errores si los hay, pero limitar el número para no hacer la respuesta demasiado grande
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
@role_required(['porteria', 'administrador'])
def parking(request):
    return render(request, 'parking/inicio_parqueo.html')


@login_required
def zonas_comunes(request):
    return render(request, 'zonas_comunes.html')


# Clave secreta para encriptar/desencriptar
SECRET_KEY = b'Gm1U9cXOTymMtcdHpD8eFwXVVHF7o4F6AoIVJGAJ5K4='
cipher = Fernet(SECRET_KEY)


@login_required
def bienvenida(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Generar token único
                uuid_token = str(uuid.uuid4())
                
                # Obtener el tipo de visitante
                tipo_visitante = request.POST.get('tipo_visitante', 'peatonal')
                
                # Datos comunes para ambos tipos de visitantes
                datos_visitante = {
                    'email': request.POST['email'],
                    'nombre': request.POST['nombre'],
                    'celular': request.POST['celular'],
                    'cedula': request.POST['cedula'],
                    'motivo': request.POST['motivo'],
                    'email_creador': request.POST['email_creador'],
                    'nombre_log': request.POST['nombre_log'],
                    'token': uuid_token,
                    'fecha_generacion': timezone.now(),
                    'numper': request.POST['numper'],
                    'usuario_id': request.user.conjunto_id,
                    'ultima_lectura': None
                }
                
                # Crear el visitante según el tipo
                if tipo_visitante == 'vehicular':
                    visitante = VisitanteVehicular.objects.create(
                        **datos_visitante,
                        tipo_vehiculo=request.POST['tipo_vehiculo'],
                        placa=request.POST['placa'].upper(),
                        segunda_lectura=None
                    )
                else:
                    visitante = Visitante.objects.create(**datos_visitante)
                
                logger.info(f"Visitante {tipo_visitante} creado - ID: {visitante.id}")

                # Generar y enviar QR
                raw_token = f"Kislev_{tipo_visitante}_{uuid_token}"  # Incluimos el tipo en el token
                encrypted_token = cipher.encrypt(raw_token.encode()).decode()
                
                # Generar URL del QR - Ahora siempre usa validar_qr
                base_url = f"https://{request.get_host()}" if 'railway.app' in request.get_host() else request.build_absolute_uri('/').rstrip('/')
                enlace_qr = f"{base_url}{reverse('validar_qr', args=[encrypted_token])}"

                # Generar QR y enviarlo por email
                qr_dir = os.path.join(settings.MEDIA_ROOT, 'qrs')
                os.makedirs(qr_dir, exist_ok=True)
                qr_file_path = os.path.join(qr_dir, f'qr_{visitante.id}.png')
                
                # Generar QR
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
                qr.add_data(enlace_qr)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_img.save(qr_file_path)

                # Preparar mensaje de email según tipo de visitante
                mensaje_adicional = ""
                if tipo_visitante == 'vehicular':
                    mensaje_adicional = f"\n\nNota: Este código QR es válido para registrar tanto la entrada como la salida del vehículo."

                # Enviar email
                try:
                    # Sanitizar todos los datos antes de enviar
                    nombre_limpio = sanitize_text(visitante.nombre)
                    email_limpio = sanitize_text(visitante.email)
                    mensaje_limpio = sanitize_text(mensaje_adicional) if mensaje_adicional else ""
                    
                    email_message = EmailMessage(
                        sanitize_text("Tu Codigo QR de Visitante"),
                        sanitize_text(f"Hola {nombre_limpio},\n\nAdjunto encontraras tu codigo QR para la visita.{mensaje_limpio}"),
                        sanitize_text(settings.DEFAULT_FROM_EMAIL),
                        [email_limpio]
                    )
                    email_message.attach_file(qr_file_path)
                    email_message.send()
                    logger.info(f"QR enviado exitosamente a {email_limpio}")
                except Exception as e:
                    logger.error(f"Error enviando email: {str(e)}")

                # Limpiar archivo temporal
                try:
                    os.remove(qr_file_path)
                except:
                    pass

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
            usuario_id=conjunto_id
        )

        # Análisis de visitantes recurrentes - Filtrado por conjunto
        correos_recurrentes = Visitante.objects.filter(
            usuario_id=conjunto_id
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
            usuario_id=conjunto_id
        ).count()

        # Total de pendientes
        total_pendientes = pendientes_hoy + pendientes_anteriores

        # Datos para el gráfico por año seleccionado
        año_inicio = timezone.make_aware(datetime(año_seleccionado, 1, 1))
        año_fin = timezone.make_aware(datetime(año_seleccionado, 12, 31, 23, 59, 59))
        
        visitantes_por_mes = Visitante.objects.filter(
            ultima_lectura__isnull=False,
            ultima_lectura__range=(año_inicio, año_fin),
            usuario_id=conjunto_id
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
            'conjunto_id': conjunto_id
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
        usuario_id=conjunto_id
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
        usuario_id=conjunto_id,  # Cambiado para usar usuario_id directamente
        tipo_vehiculo='carro',
        ultima_lectura__isnull=False,
        segunda_lectura__isnull=True
    ).order_by('-ultima_lectura')
    
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
        usuario_id=conjunto_id,  # Cambiado para usar usuario_id directamente
        tipo_vehiculo='moto',
        ultima_lectura__isnull=False,
        segunda_lectura__isnull=True
    ).order_by('-ultima_lectura')
    
    context = {
        'disponibilidad': disponibilidad,
        'vehiculos_activos': vehiculos_activos,
        'conjunto': request.user.conjunto,
    }
    
    return render(request, 'parking/disponibilidad_tipo.html', context)

@login_required
def historial_vehiculos(request, tipo_vehiculo):
    """Vista para mostrar el historial de movimientos de vehículos"""
    conjunto_id = request.user.conjunto_id
    
    # Obtener todos los movimientos del tipo de vehículo especificado
    movimientos = VisitanteVehicular.objects.filter(
        usuario__conjunto_id=conjunto_id,
        tipo_vehiculo=tipo_vehiculo,
        ultima_lectura__isnull=False
    ).select_related('usuario').order_by('-ultima_lectura')
    
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
        
        return JsonResponse({
            'status': 'success',
            'apartamentos': apartamentos,
            'ocupados': list(ocupados)
        })
    except Exception as e:
        logger.error(f"Error al obtener apartamentos: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error al cargar los apartamentos'
        }, status=500)