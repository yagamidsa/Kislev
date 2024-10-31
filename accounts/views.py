# accounts/views.py
# accounts/views.py
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views import View
from django import forms
from django.contrib.auth.views import (
    LogoutView as DjangoLogoutView,
    PasswordResetView,
    PasswordResetConfirmView
)
from django.urls import reverse_lazy
from django.contrib.auth.forms import SetPasswordForm  # Agregar esta importación
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.utils.translation import gettext as _  # Para traducciones
from .utils import role_required
from .forms import LoginForm
from accounts.models import Usuario
from django.contrib.auth.views import LogoutView as DjangoLogoutView


@method_decorator(role_required(['administrador']), name='dispatch')
class VisorAdminView(TemplateView):
    template_name = 'accounts/visor_admin.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        context = {'user': user}
        return self.render_to_response(context)
    
    
    

@method_decorator([login_required, role_required(['porteria', 'administrador'])], name='dispatch')
class ControlPorteriaView(TemplateView):
    template_name = 'accounts/control_porteria.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        context = {'user': user}
        return self.render_to_response(context)


@method_decorator([login_required, role_required(['propietario', 'administrador'])], name='dispatch')
class ControlpropietarioView(TemplateView):
    template_name = 'accounts/visor_propietario.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        context = {'user': user}
        return self.render_to_response(context)

    


@method_decorator(csrf_protect, name='dispatch')
class LoginView(View):
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return self._redirect_by_user_type(request.user)
            
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            cedula = form.cleaned_data.get('cedula')
            conjunto = form.cleaned_data.get('conjunto')
            password = form.cleaned_data.get('password')

            # Autenticar usando el backend personalizado
            user = authenticate(
                request, 
                cedula=cedula, 
                conjunto=conjunto, 
                password=password
            )

            if user is not None:
                login(request, user)
                if request.is_secure():
                    request.session.cookie_secure = True
                
                # Registrar el último acceso
                user.save()
                
                return self._redirect_by_user_type(user)
            else:
                messages.error(
                    request, 
                    'Credenciales inválidas. Por favor, verifique su cédula y contraseña.'
                )

        return render(request, self.template_name, {'form': form})

    def _redirect_by_user_type(self, user):
        """Helper method para manejar las redirecciones según el tipo de usuario"""
        redirects = {
            'propietario': 'accounts:visor_propietario',
            'administrador': 'accounts:visor_admin',
            'porteria': 'accounts:control_porteria'
        }
        return redirect(redirects.get(user.user_type, 'accounts:login'))

@method_decorator(csrf_protect, name='dispatch')
class LogoutView(DjangoLogoutView):
    def dispatch(self, request, *args, **kwargs):
        # Verificar si el usuario está autenticado
        if request.user.is_authenticated:
            # Realizar el logout
            logout(request)
            # Agregar mensaje de éxito
            messages.success(request, 'Has cerrado sesión correctamente.')
        
        # Redirigir a la página de inicio o login
        return redirect('accounts:login')  # Puedes cambiar '/' por el nombre de tu URL, ejemplo: 'login'

    def get_next_page(self):
        return 'login'  # O la URL que desees

from django.contrib.auth.views import PasswordResetView

class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/reset_password.html'  # Agregado accounts/
    email_template_name = 'accounts/password_reset_email.html'  # Agregado accounts/
    subject_template_name = 'accounts/password_reset_subject.txt'  # Agregado accounts/
    success_url = reverse_lazy('accounts:password_reset_done')  # Usar reverse_lazy

    def form_valid(self, form):
        email = form.cleaned_data['email']
        if not Usuario.objects.filter(email=email).exists():
            messages.error(self.request, 'No hay una cuenta asociada a ese correo electrónico.')
            return self.form_invalid(form)

        response = super().form_valid(form)
        messages.success(self.request, 'Se ha enviado un enlace para restablecer la contraseña al correo electrónico mencionado.')
        return response

class CustomSetPasswordForm(SetPasswordForm):
    def clean_new_password1(self):
        new_password1 = self.cleaned_data.get('new_password1')
        
        if len(new_password1) < 8:
            raise forms.ValidationError(_("La contraseña debe tener al menos 8 caracteres."))

        return new_password1

    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')

        if new_password1 and new_password2 and new_password1 != new_password2:
            raise forms.ValidationError(_("Las contraseñas no coinciden."))

        return cleaned_data
    
    

class CustomPasswordChangeView(View):
    def get(self, request, *args, **kwargs):
        form = CustomSetPasswordForm(user=request.user)
        return render(request, 'accounts/reset_password.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = CustomSetPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu contraseña ha sido cambiada con éxito.')
            return redirect('accounts:login')  # Agregado namespace
        else:
            messages.error(request, 'Por favor, corrige los errores a continuación.')
        
        return render(request, 'accounts/reset_password.html', {'form': form})
    
     
    

from django.views.generic import TemplateView

class PasswordResetDoneView(TemplateView):
    template_name = 'accounts/password_reset_done.html'