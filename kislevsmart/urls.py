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
    path('validar_qr/<str:encrypted_token>/', views.validar_qr, name='validar_qr'),
    path('valqr/<str:email_b64>/', views.success_page, name='valqr'),
    path('leerscaner/', views.leerscaner, name='leerscaner'),
    path('notificaciones/', views.notificaciones, name='notificaciones'),
    path('parking/', views.parking, name='parking'),
    path('zonas_comunes/', views.zonas_comunes, name='zonas_comunes'),
    path('carros/', views.disponibilidad_carros, name='disponibilidad_carros'),
    path('motos/', views.disponibilidad_motos, name='disponibilidad_motos'),
    
    # Rutas de notificaciones
    path('noti_generales/', views.noti_generales, name='noti_generales'),
    path('noti_individual/', views.noti_individual, name='noti_individual'),
    path('noti_publicos/', views.noti_publicos, name='noti_publicos'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # APIs
    path('api/send-service-notification/', views.send_service_notification, name='send_service_notification'),
    path('notifications/send/', views.procesar_envio, name='procesar_envio'),
    
    # Rutas de salas
    path('salas/', views.SalaListView.as_view(), name='lista_salas'),
    path('sala/<int:sala_id>/calendario/', views.calendario_sala, name='calendario_sala'),
    path('api/sala/<int:sala_id>/reservas/', views.get_reservas_sala, name='api_reservas_sala'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('reserva/<int:reserva_id>/cancelar/', views.cancelar_reserva, name='cancelar_reserva'),
    path('sala/<int:sala_id>/reservar/', views.reservar_sala, name='reservar_sala'),
    path('api/sala/<int:sala_id>/horarios/<str:fecha>/', views.get_horarios_disponibles, name='api_horarios_disponibles'),
    path('visitor-stats/', views.get_visitor_stats, name='visitor-stats'),
]

# Configuración de archivos estáticos y media para desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)