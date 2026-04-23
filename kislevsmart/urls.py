"""kislevsmart URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# kislevsmart/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views
from django.shortcuts import render

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Ruta raíz
    path('', lambda request: render(request, 'index.html'), name='home'),
    
    # Incluir las URLs de accounts con su namespace
    path('accounts/', include('accounts.urls', namespace='accounts')),
    
    # Rutas existentes de la aplicación
    path('bienvenida/', views.bienvenida, name='bienvenida'),
    path('visitantes-guardados/', views.visitantes_guardados_api, name='visitantes_guardados_api'),
    path('mis-frecuentes/', views.mis_frecuentes, name='mis_frecuentes'),
    path('admin/frecuentes/', views.admin_frecuentes, name='admin_frecuentes'),
    path('validar_qr/<str:encrypted_token>/', views.validar_qr, name='validar_qr'),
    path('valqr/<str:email_b64>/', views.success_page, name='valqr'),
    path('leerscaner/', views.leerscaner, name='leerscaner'),
    path('notificaciones/', views.notificaciones, name='notificaciones'),
    path('parking/', views.parking, name='parking'),
    path('carros/', views.disponibilidad_carros, name='disponibilidad_carros'),
    path('motos/', views.disponibilidad_motos, name='disponibilidad_motos'),
    path('parqueadero/metricas/<str:tipo>/', views.metricas_parqueadero, name='metricas_parqueadero'),
    path('parking/config/', views.config_parqueadero, name='config_parqueadero'),
    
    # Rutas de notificaciones
    path('noti_generales/', views.noti_generales, name='noti_generales'),
    path('noti_individual/', views.noti_individual, name='noti_individual'),
    path('noti_publicos/', views.noti_publicos, name='noti_publicos'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # APIs
    path('api/send-service-notification/', views.send_service_notification, name='send_service_notification'),
    path('notifications/send/', views.procesar_envio, name='procesar_envio'),
    path('api/torres/', views.get_torres, name='get_torres'),
    path('api/torres/<int:torre_id>/apartamentos/', views.get_apartamentos, name='get_apartamentos'),
    path('api/send-individual-notification/', views.enviar_notificacion_individual, name='enviar_notificacion_individual'),
    
    # Rutas de salas
    path('salas/', views.SalaListView.as_view(), name='lista_salas'),
    path('sala/<int:sala_id>/calendario/', views.calendario_sala, name='calendario_sala'),
    path('api/sala/<int:sala_id>/reservas/', views.get_reservas_sala, name='api_reservas_sala'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('reserva/<int:reserva_id>/cancelar/', views.cancelar_reserva, name='cancelar_reserva'),
    path('reserva/<int:reserva_id>/aprobar/', views.aprobar_reserva, name='aprobar_reserva'),
    path('salas/bloquear/', views.bloquear_sala, name='bloquear_sala'),

    # Módulo de paquetes / mensajería
    path('paquetes/', views.lista_paquetes, name='lista_paquetes'),
    path('paquetes/registrar/', views.registrar_paquete, name='registrar_paquete'),
    path('paquetes/entregar/', views.entregar_paquete, name='entregar_paquete'),
    path('paquetes/metricas/', views.metricas_paquetes, name='metricas_paquetes'),
    path('api/paquetes/kpi/', views.dashboard_kpi_paquetes, name='dashboard_kpi_paquetes'),
    path('api/paquetes/editar/', views.editar_paquete, name='editar_paquete'),
    path('sala/<int:sala_id>/reservar/', views.reservar_sala, name='reservar_sala'),
    path('api/sala/<int:sala_id>/horarios/<str:fecha>/', views.get_horarios_disponibles, name='api_horarios_disponibles'),
    path('visitor-stats/', views.get_visitor_stats, name='visitor-stats'),
    path('mis-visitantes/', views.historial_visitantes, name='historial_visitantes'),
    path('mis-visitantes/<int:visitante_id>/regenerar-qr/', views.regenerar_qr_visitante, name='regenerar_qr_visitante'),

    # Reporte PDF
    path('reporte-mensual/', views.reporte_pdf_mensual, name='reporte_pdf_mensual'),

    # Módulo de novedades
    path('novedades/', views.lista_novedades, name='lista_novedades'),
    path('novedades/<int:pk>/', views.detalle_novedad, name='detalle_novedad'),
    path('novedades/<int:pk>/comentar/', views.agregar_comentario, name='agregar_comentario'),
    path('novedades/crear/', views.crear_novedad, name='crear_novedad'),
    path('novedades/<int:pk>/eliminar/', views.eliminar_novedad, name='eliminar_novedad'),
    path('novedades/<int:pk>/like/', views.toggle_like, name='toggle_like'),
    path('novedades/metricas/', views.metricas_novedades, name='metricas_novedades'),

    # Módulo financiero
    path('finanzas/', views.finanzas_admin, name='finanzas_admin'),
    path('finanzas/cuota/crear/', views.crear_cuota, name='crear_cuota'),
    path('finanzas/cuota/<int:cuota_id>/pago/', views.registrar_pago, name='registrar_pago'),
    path('mi-estado-cuenta/', views.estado_cuenta, name='estado_cuenta'),

    # Mantenimiento interno — llamado por cron externo con token secreto
    path('_maint/', views.mantenimiento_cron, name='mantenimiento_cron'),
]

# Configuración de archivos estáticos y media para desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)