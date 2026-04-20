# accounts/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from .views import (
    LoginView,
    LogoutView,
    CustomPasswordResetView,
    CustomPasswordChangeView,
    RecuperarPasswordView,
    RecuperarPasswordConfirmView,
    PasswordResetDoneView,
    VisorAdminView,
    ControlPorteriaView,
    ControlpropietarioView,
    SelectConjuntoView,
    ForcePasswordChangeView,
    saas_dashboard,
    download_template,
    upload_conjunto,
    gestion_usuarios,
    toggle_usuario_activo,
    editar_usuario,
    exportar_usuarios_excel,
    crear_usuario,
    gestionar_conjunto,
    update_config_global,
    update_conjunto_config,
    update_mi_conjunto,
    toggle_conjunto_activo,
    eliminar_conjunto,
)

app_name = 'accounts'  # Namespace para las URLs de accounts

urlpatterns = [
    # Rutas de autenticación principales
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('select-conjunto/', SelectConjuntoView.as_view(), name='select_conjunto'),
    
    # Cambiar contraseña (usuario logueado)
    path('cambiar-password/', CustomPasswordChangeView.as_view(), name='cambiar_password'),

    # Olvidé mi contraseña — link firmado por email (seguro)
    path('recuperar-password/', RecuperarPasswordView.as_view(), name='recuperar_password'),
    path('recuperar-password/confirmar/<str:token>/', RecuperarPasswordConfirmView.as_view(), name='recuperar_confirmar'),

    # Rutas de recuperación de contraseña por email (legacy)
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

    # Primer login — cambio obligatorio de contraseña
    path('force-password-change/', ForcePasswordChangeView.as_view(), name='force_password_change'),

    # SaaS owner panel
    path('saas/', saas_dashboard, name='saas_dashboard'),
    path('saas/download-template/', download_template, name='download_template'),
    path('saas/upload-conjunto/', upload_conjunto, name='upload_conjunto'),
    path('saas/conjunto/<int:conjunto_id>/', gestionar_conjunto, name='gestionar_conjunto'),
    path('saas/config/', update_config_global, name='update_config_global'),
    path('saas/conjunto/<int:conjunto_id>/config/', update_conjunto_config, name='update_conjunto_config'),
    path('saas/conjunto/<int:conjunto_id>/toggle/', toggle_conjunto_activo, name='toggle_conjunto_activo'),
    path('saas/conjunto/<int:conjunto_id>/eliminar/', eliminar_conjunto, name='eliminar_conjunto'),

    # Páginas legales (públicas)
    path('politica-privacidad/', TemplateView.as_view(template_name='accounts/politica_privacidad.html'), name='politica_privacidad'),
    path('terminos-condiciones/', TemplateView.as_view(template_name='accounts/terminos_condiciones.html'), name='terminos_condiciones'),

    # Admin — editar info de su propio conjunto
    path('mi-conjunto/config/', update_mi_conjunto, name='update_mi_conjunto'),

    # Gestión de usuarios
    path('residentes/', gestion_usuarios, name='gestion_usuarios'),
    path('residentes/crear/', crear_usuario, name='crear_usuario'),
    path('usuarios/<int:usuario_id>/toggle/', toggle_usuario_activo, name='toggle_usuario_activo'),
    path('usuarios/<int:usuario_id>/editar/', editar_usuario, name='editar_usuario'),
    path('residentes/exportar/', exportar_usuarios_excel, name='exportar_usuarios_excel'),
]