# accounts/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    LoginView, 
    LogoutView, 
    CustomPasswordResetView,
    PasswordResetDoneView, 
    VisorAdminView, 
    ControlPorteriaView, 
    ControlpropietarioView
)

app_name = 'accounts'  # Namespace para las URLs de accounts

urlpatterns = [
    # Rutas de autenticación principales
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # Rutas de recuperación de contraseña
    path('password_reset/', CustomPasswordResetView.as_view(
        template_name='accounts/reset_password.html',
        email_template_name='accounts/password_reset_email.html',
        subject_template_name='accounts/password_reset_subject.txt',
        success_url='/accounts/password_reset/done/'
    ), name='reset_password'),
    
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/reset_password_sent.html'
    ), name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/reset_password_form.html',
        success_url='/accounts/reset/done/'
    ), name='password_reset_confirm'),
    
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/reset_password_complete.html'
    ), name='password_reset_complete'),
    
    # Rutas de vistas protegidas por tipo de usuario
    path('visor_admin/', VisorAdminView.as_view(), name='visor_admin'),
    path('visor_propietario/', ControlpropietarioView.as_view(), name='visor_propietario'),
    path('control_porteria/', ControlPorteriaView.as_view(), name='control_porteria'),
]