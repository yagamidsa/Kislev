import base64
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
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
from accounts.models import Usuario
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

        # 2. Preparar mensaje
        mensaje_usuario = mensaje_usuario.replace('\n', '<br>')

        # 3. Obtener propietarios
        propietarios = Usuario.objects.filter(
            user_type='propietario',
            is_active=True
        ).values('email', 'nombre')

        total_propietarios = propietarios.count()
        if not total_propietarios:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay propietarios activos'
            })

        # 4. Inicializar SendGrid
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        
        # 5. Procesar archivo adjunto si existe
        attachment = None
        if request.FILES.get('fileInput'):
            try:
                archivo = request.FILES['fileInput']
                encoded_file = base64.b64encode(archivo.read()).decode()
                
                attachment = Attachment()
                attachment.file_content = FileContent(encoded_file)
                attachment.file_name = FileName(archivo.name)
                attachment.file_type = FileType(archivo.content_type)
                attachment.disposition = Disposition('attachment')
                logger.info(f"Archivo adjunto procesado: {archivo.name}")
            except Exception as e:
                logger.error(f"Error procesando archivo: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Error procesando el archivo adjunto'
                })

        # 6. Preparar envío por lotes
        BATCH_SIZE = 500
        total_enviados = 0
        propietarios_list = list(propietarios)
        
        # 7. Procesar cada lote
        for i in range(0, len(propietarios_list), BATCH_SIZE):
            batch = propietarios_list[i:i + BATCH_SIZE]
            first_prop = batch[0]
            other_props = batch[1:]
            
            # 8. Construir mensaje HTML
            mensaje_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin: 0; padding: 0; font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="margin-bottom: 20px;">
                        <p style="font-size: 16px; color: #333; margin: 0;">Estimado(a) {first_prop['nombre']},</p>
                    </div>
                    
                    <div style="margin: 30px 0; line-height: 1.6; color: #444;">
                        {mensaje_usuario}
                    </div>
                    
                    <div style="border-top: 1px solid #eee; padding-top: 20px; margin-top: 30px;">
                        <p style="font-size: 14px; color: #666; margin: 5px 0;">
                            Este es un mensaje oficial de la administración.
                        </p>
                        <div style="margin: 15px 0;">
                            <p style="font-size: 14px; color: #444; margin: 3px 0;">📞 (601) XXX-XXXX</p>
                            <p style="font-size: 14px; color: #444; margin: 3px 0;">📧 admin@conjunto.com</p>
                        </div>
                        <p style="font-size: 12px; color: #888; margin-top: 20px;">
                            © 2024 Administración Conjunto Residencial<br>
                            Recibió este email porque está registrado como propietario en nuestro sistema.
                            Para dejar de recibir estos mensajes, por favor contacte a la administración.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """

            # 9. Crear mensaje de correo
            message = Mail(
                from_email=Email(settings.DEFAULT_FROM_EMAIL),
                to_emails=To(first_prop['email']),
                subject='Notificación General',
                html_content=mensaje_html,
                plain_text_content=mensaje_usuario.replace('<br>', '\n')
            )

            # 10. Agregar destinatarios BCC
            for prop in other_props:
                message.add_bcc(prop['email'])

            # 11. Agregar adjunto si existe
            if attachment:
                message.add_attachment(attachment)

            # 12. Enviar lote
            try:
                response = sg.send(message)
                if response.status_code in [200, 201, 202]:
                    total_enviados += len(batch)
                    logger.info(f"Lote enviado: {i//BATCH_SIZE + 1}, Total: {total_enviados}/{total_propietarios}")
                else:
                    logger.warning(f"Respuesta inesperada en lote {i//BATCH_SIZE + 1}: {response.status_code}")
            except Exception as e:
                logger.error(f"Error enviando lote {i//BATCH_SIZE + 1}: {str(e)}")
                continue

        # 13. Retornar resultado
        if total_enviados > 0:
            return JsonResponse({
                'status': 'success',
                'enviados': total_enviados,
                'total': total_propietarios
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'No se pudo completar el envío de mensajes'
            })

    except Exception as e:
        logger.error(f"Error general: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error en el sistema'
        })




# views.py --- s.Publicos


BATCH_SIZE = 500  # Tamaño del lote
DELAY_BETWEEN_BATCHES = 2  # Segundos entre lotes

@require_POST
def send_service_notification(request):
    try:
        data = json.loads(request.body)
        service_type = data.get('service_type')
        
        # Obtener todos los propietarios
        propietarios = list(Usuario.objects.filter(
            user_type='propietario',
            is_active=True
        ))

        total_users = len(propietarios)
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        successful_sends = 0
        failed_sends = 0
        errors = []

        # Dividir en lotes de 500
        batches = [propietarios[i:i + BATCH_SIZE] for i in range(0, total_users, BATCH_SIZE)]
        total_batches = len(batches)

        for batch_index, batch in enumerate(batches, 1):
            batch_successful = 0
            batch_failed = 0

            for propietario in batch:
                try:
                    # Crear contenido HTML
                    html_content = render_to_string('emails/service_notification.html', {
                        'nombre': propietario.nombre,
                        'service_type': service_type
                    })
                    
                    # Crear versión texto plano
                    plain_content = f"""
                        Estimado/a {propietario.nombre},
                        
                        Su factura de {service_type} está disponible para retiro en portería.
                        
                        Por favor, pase a retirarla en horario de atención.
                        
                        Saludos cordiales,
                        Tu Empresa
                    """

                    # Crear mensaje con configuraciones anti-spam
                    message = Mail(
                        from_email=From(
                            email=settings.DEFAULT_FROM_EMAIL,
                            name="Administración Conjunto Residencial"
                        ),
                        to_emails=To(
                            email=propietario.email,
                            name=propietario.nombre
                        ),
                        subject=Subject(f'Notificación: Su factura de {service_type} está disponible'),
                        plain_text_content=PlainTextContent(plain_content),
                        html_content=HtmlContent(html_content)
                    )

                    # Añadir headers anti-spam
                    message.header = Header("List-Unsubscribe", f"<mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>")
                    message.header = Header("Precedence", "bulk")
                    message.header = Header("X-Auto-Response-Suppress", "OOF, AutoReply")
                    message.category = Category("notificaciones_servicios")
                    message.custom_arg = CustomArg("type", "service_notification")
                    message.custom_arg = CustomArg("service", service_type)
                    message.reply_to = settings.DEFAULT_FROM_EMAIL

                    # Enviar email
                    response = sg.send(message)
                    
                    if response.status_code in [200, 201, 202]:
                        batch_successful += 1
                        successful_sends += 1
                    else:
                        batch_failed += 1
                        failed_sends += 1
                        errors.append(f"Error con {propietario.email}: Status code {response.status_code}")

                except Exception as e:
                    batch_failed += 1
                    failed_sends += 1
                    errors.append(f"Error con {propietario.email}: {str(e)}")

            # Calcular progreso después de cada lote
            progress = (batch_index / total_batches) * 100
            
            # Devolver progreso parcial
            progress_data = {
                'status': 'processing',
                'batch_index': batch_index,
                'total_batches': total_batches,
                'progress': round(progress, 1),
                'successful_sends': successful_sends,
                'failed_sends': failed_sends,
                'total_users': total_users,
                'current_batch_size': len(batch),
                'remaining_batches': total_batches - batch_index
            }

            print(f"Progreso: {progress_data}")  # Para debugging

            # Esperar entre lotes para no sobrecargar
            if batch_index < total_batches:
                time.sleep(DELAY_BETWEEN_BATCHES)

        # Preparar respuesta final
        final_response = {
            'status': 'success' if successful_sends > 0 else 'error',
            'message': f'Proceso completado: {successful_sends} exitosos, {failed_sends} fallidos',
            'successful_sends': successful_sends,
            'failed_sends': failed_sends,
            'total_processed': total_users,
            'total_batches': total_batches,
            'errors': errors[:5] if errors else None,  # Mostrar solo los primeros 5 errores
            'completion_percentage': 100
        }

        return JsonResponse(final_response)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error en el proceso: {str(e)}',
            'successful_sends': successful_sends if 'successful_sends' in locals() else 0,
            'failed_sends': failed_sends if 'failed_sends' in locals() else 0,
            'total_users': total_users if 'total_users' in locals() else 0
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
                
                # Crear visitante
                visitante = Visitante.objects.create(
                    email=request.POST['email'],
                    nombre=request.POST['nombre'],
                    celular=request.POST['celular'],
                    cedula=request.POST['cedula'],
                    motivo=request.POST['motivo'],
                    email_creador=request.POST['email_creador'],
                    nombre_log=request.POST['nombre_log'],
                    token=uuid_token,
                    fecha_generacion=timezone.now(),
                    numper=request.POST['numper'],
                    ultima_lectura=None
                )
                
                logger.info(f"Visitante creado - ID: {visitante.id}")

                # Generar y enviar QR
                raw_token = f"Kislev_{uuid_token}"
                encrypted_token = cipher.encrypt(raw_token.encode()).decode()
                
                # Generar URL del QR
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

                # Enviar email
                try:
                    email_message = EmailMessage(
                        "Tu Código QR de Visitante",
                        f"Hola {visitante.nombre},\n\nAdjunto encontrarás tu código QR para la visita.",
                        settings.DEFAULT_FROM_EMAIL,
                        [visitante.email]
                    )
                    email_message.attach_file(qr_file_path)
                    email_message.send()
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
                    # Si es una petición AJAX
                    return JsonResponse({
                        'status': 'success',
                        'redirect_url': reverse('valqr', kwargs={'email_b64': email_b64}),
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
        return HttpResponse(status=204)  # No Content

    # Verificar fuente del escaneo
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
                Visitante.objects.select_for_update(nowait=True),
                token=original_token
            )
            
            # Verificar estado directamente en la base de datos
            visitante.refresh_from_db()
            
            # Detectar si es una solicitud desde Safari/iOS
            is_safari = 'Safari' in request.META.get('HTTP_USER_AGENT', '')
            
            if visitante.ultima_lectura is not None:
                logger.warning(f"QR ya utilizado el: {visitante.ultima_lectura}")
                # Si es Safari/iOS y es la primera vez que se intenta, dar una segunda oportunidad
                if is_safari and 'attempted' not in request.session:
                    request.session['attempted'] = True
                    logger.info("Primera intención desde Safari - permitiendo segundo intento")
                    return render(request, 'validar_qr.html', {'visitante': visitante})
                return render(request, 'qr_desactivado.html', {
                    'mensaje': 'Este código QR ya ha sido utilizado.',
                    'ultima_lectura': visitante.ultima_lectura
                })

            # Intentar registrar la lectura directamente
            visitante.ultima_lectura = timezone.now()
            visitante.nombre_log = request.user.email
            visitante.save()
            
            # Limpiar la sesión
            if 'attempted' in request.session:
                del request.session['attempted']
            
            logger.info(f"Lectura registrada exitosamente: {visitante.ultima_lectura}")
            return render(request, 'validar_qr.html', {'visitante': visitante})

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
@role_required(['porteria', 'administrador'])
def dashboard(request):
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
            # Convertir la fecha string a datetime con zona horaria
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

    # Consultas base - usando rango de fecha en lugar de __date
    visitantes_dia = Visitante.objects.filter(
        fecha_generacion__range=(fecha_inicio, fecha_fin)
    )

    # Análisis de visitantes recurrentes
    correos_recurrentes = Visitante.objects.values('email').annotate(
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
        fecha_generacion__gte=tiempo_limite
    ).count()

    # Total de pendientes
    total_pendientes = pendientes_hoy + pendientes_anteriores

    # Datos para el gráfico por año seleccionado
    año_inicio = timezone.make_aware(datetime(año_seleccionado, 1, 1))
    año_fin = timezone.make_aware(datetime(año_seleccionado, 12, 31, 23, 59, 59))
    
    visitantes_por_mes = Visitante.objects.filter(
        ultima_lectura__isnull=False,
        ultima_lectura__range=(año_inicio, año_fin)
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
    # Conteo de visitantes por motivo para el día seleccionado
    visitantes_por_motivo = visitantes_dia.values('motivo').annotate(
        total=Count('id')
    ).order_by('-total')  # Ordenar por cantidad descendente

    # En tu vista, después de la consulta de visitantes_por_motivo
    total_visitantes_dia = visitantes_dia.count()

    # Conteo de visitantes por motivo para el día seleccionado
    visitantes_por_motivo = visitantes_dia.values('motivo').annotate(
        total=Count('id')
    ).order_by('-total')
    
    
    
    
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



    # Obtener visitantes por día de la semana y hora


        
    # Contexto para el template
    context = {
        'fecha_seleccionada': fecha_inicio.date(),  # Convertimos a date para el template
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
    }
    
    return render(request, 'dashboard.html', context)


#consulta por hora
def get_visitor_stats(request):
    # Obtener el tipo de filtro desde la solicitud
    filter_type = request.GET.get('filter_type', 'week')
    selected_month = int(request.GET.get('month', datetime.now().month))
    selected_year = int(request.GET.get('year', datetime.now().year))
    
    # Consulta base
    base_query = Visitante.objects.exclude(ultima_lectura__isnull=True)
    
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
        
        # Asegurarse de que todos los días estén representados
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
        
        # Asegurarse de que todos los meses estén representados
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
        
        # Asegurarse de que todas las horas estén representadas
        all_data = {hour: 0 for hour in range(24)}
        for stat in stats:
            all_data[stat['hour']] = stat['count']
        
        labels = [f'{hour:02d}:00' for hour in range(24)]
        data = [all_data[hour] for hour in range(24)]
    
    return JsonResponse({
        'labels': labels,
        'data': data
    })