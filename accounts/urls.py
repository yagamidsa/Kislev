# accounts/urls.py
from django.urls import path
from .views import (
    LoginView, LogoutView, CustomPasswordResetView, 
    PasswordResetDoneView, VisorAdminView, ControlPorteriaView, ControlpropietarioView
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password_reset/', CustomPasswordResetView.as_view(), name='reset_password'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/reset_password_sent.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/reset_password_form.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/reset_password_complete.html'), name='password_reset_complete'),
    path('password_reset_done/', PasswordResetDoneView.as_view(), name='password_reset_done'),
    
    # Asegúrate de usar la vista protegida aquí
    path('visor_admin/', VisorAdminView.as_view(), name='visor_admin'),
    path('visor_propietario/', ControlpropietarioView.as_view(), name='visor_propietario'),
    path('control_porteria/', ControlPorteriaView.as_view(), name='control_porteria'),
]
