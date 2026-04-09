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
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.utils.translation import gettext as _
from django.core import signing
import time
from django_ratelimit.decorators import ratelimit
from .utils import role_required
from .forms import LoginForm, SelectConjuntoForm
from .models import Usuario, ConjuntoResidencial
from kislevsmart.models import Novedad, NovedadVista, Visitante, VisitanteVehicular, ConfigParqueadero
from kislevsmart.utils import calcular_cobro_parqueadero
from django.utils import timezone as tz


# Mantenemos las vistas existentes
@method_decorator(role_required(['administrador']), name='dispatch')
class VisorAdminView(TemplateView):
    template_name = 'accounts/visor_admin.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        conjunto = user.conjunto
        hoy = tz.localdate()
        visitantes_hoy = Visitante.objects.filter(conjunto=conjunto, fecha_generacion__date=hoy).count()
        residentes = Usuario.objects.filter(conjunto=conjunto, user_type='propietario', is_active=True).count()
        from kislevsmart.models import Reserva
        reservas_pendientes = Reserva.objects.filter(sala__conjunto=conjunto, estado='pendiente').count()
        vehiculos_dentro = VisitanteVehicular.objects.filter(
            conjunto=conjunto,
            ultima_lectura__isnull=False,
            segunda_lectura__isnull=True,
        ).count()
        context = {
            'user': user,
            'visitantes_hoy': visitantes_hoy,
            'residentes': residentes,
            'reservas_pendientes': reservas_pendientes,
            'vehiculos_dentro': vehiculos_dentro,
        }
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
        vistas_ids = NovedadVista.objects.filter(
            usuario=user
        ).values_list('novedad_id', flat=True)
        novedades_no_vistas = Novedad.objects.filter(
            conjunto=user.conjunto,
            activa=True,
        ).exclude(id__in=vistas_ids).order_by('-created_at')

        # Vehículos visitantes activos del propietario
        vehiculos_qs = VisitanteVehicular.objects.filter(
            conjunto=request.user.conjunto,
            tipo_vehiculo__in=['carro', 'moto'],
            ultima_lectura__isnull=False,
            segunda_lectura__isnull=True,
            email_creador=request.user.email
        ).order_by('-ultima_lectura')

        vehiculos_activos = []
        for v in vehiculos_qs:
            config = ConfigParqueadero.objects.filter(
                conjunto=request.user.conjunto,
                tipo_vehiculo=v.tipo_vehiculo
            ).first()
            valor, mins, en_gracia = calcular_cobro_parqueadero(v.ultima_lectura, config)
            horas = mins // 60
            minutos = mins % 60
            vehiculos_activos.append({
                'placa': v.placa,
                'tipo': v.get_tipo_vehiculo_display(),
                'tiempo_str': f'{horas}h {minutos}m' if horas > 0 else f'{minutos}m',
                'valor': valor,
                'en_gracia': en_gracia,
                'entrada': tz.localtime(v.ultima_lectura).strftime('%H:%M'),
            })

        context = {
            'user': user,
            'novedades_no_vistas': novedades_no_vistas,
            'novedades_count': novedades_no_vistas.count(),
            'vehiculos_activos': vehiculos_activos,
        }
        return self.render_to_response(context)


@method_decorator(csrf_protect, name='dispatch')
@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='post')
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
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')
            if remember_me:
                request.session.set_expiry(30 * 24 * 60 * 60)  # 30 días
            else:
                request.session.set_expiry(0)  # expira al cerrar el navegador

            # Verificar si la cédula existe en algún conjunto
            conjuntos_usuario = ConjuntoResidencial.objects.filter(
                usuario__cedula=cedula,
                usuario__is_active=True,
                estado=True
            ).distinct()

            if not conjuntos_usuario.exists():
                messages.error(
                    request, 
                    'No existe un usuario con esta cédula en ningún conjunto.'
                )
                return render(request, self.template_name, {'form': form})

            # Verificamos la contraseña con cualquiera de los usuarios
            # (la contraseña debería ser la misma para todos los conjuntos)
            conjunto_example = conjuntos_usuario.first()
            user_example = Usuario.objects.filter(
                cedula=cedula,
                conjunto=conjunto_example
            ).first()

            if not user_example or not user_example.check_password(password):
                messages.error(
                    request, 
                    'Contraseña incorrecta. Por favor, verifíquela.'
                )
                return render(request, self.template_name, {'form': form})

            # Si hay solo un conjunto, autenticamos directamente
            if conjuntos_usuario.count() == 1:
                conjunto = conjuntos_usuario.first()
                user = authenticate(
                    request,
                    cedula=cedula,
                    conjunto=conjunto,
                    password=password
                )
                
                if user:
                    # Especificamos el backend
                    user.backend = 'accounts.backends.CedulaConjuntoBackend'
                    login(request, user)
                    
                    if request.is_secure():
                        request.session.cookie_secure = True
                    
                    # Registrar el último acceso
                    user.save()
                    
                    return self._redirect_by_user_type(user)
                else:
                    messages.error(request, 'Error al autenticar. Por favor, verifique sus credenciales.')
                    return render(request, self.template_name, {'form': form})
            else:
                # Si hay múltiples conjuntos, guardamos la cédula y un token firmado
                # (el token prueba que el usuario ya se autenticó correctamente)
                request.session['login_cedula'] = cedula
                request.session['login_token'] = signing.dumps(
                    {'cedula': cedula, 'ts': time.time()}, salt='kislev-login'
                )
                return redirect('accounts:select_conjunto')
        
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
class SelectConjuntoView(View):
    template_name = 'accounts/select_conjunto.html'

    def _verify_login_token(self, request):
        """Verifica el token de sesión firmado. Retorna cedula o None si inválido."""
        cedula = request.session.get('login_cedula')
        token = request.session.get('login_token')
        if not cedula or not token:
            return None
        try:
            data = signing.loads(token, salt='kislev-login', max_age=300)
            if data.get('cedula') != cedula:
                return None
        except Exception:
            return None
        return cedula

    def get(self, request):
        cedula = self._verify_login_token(request)
        if not cedula:
            messages.error(request, 'Sesión expirada. Por favor, inicie sesión nuevamente.')
            return redirect('accounts:login')

        conjuntos_usuario = ConjuntoResidencial.objects.filter(
            usuario__cedula=cedula,
            usuario__is_active=True,
            estado=True
        ).distinct()

        if not conjuntos_usuario.exists():
            messages.error(request, 'No hay conjuntos disponibles para esta cédula.')
            return redirect('accounts:login')

        if conjuntos_usuario.count() == 1:
            conjunto = conjuntos_usuario.first()
            user = Usuario.objects.filter(cedula=cedula, conjunto=conjunto, is_active=True).first()
            if user:
                user.backend = 'accounts.backends.CedulaConjuntoBackend'
                login(request, user)
                request.session.pop('login_cedula', None)
                request.session.pop('login_token', None)
                return self._redirect_by_user_type(user)
            else:
                messages.error(request, 'Error al autenticar. Credenciales inválidas.')
                return redirect('accounts:login')

        form = SelectConjuntoForm(conjuntos=conjuntos_usuario)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        cedula = self._verify_login_token(request)
        if not cedula:
            messages.error(request, 'Sesión expirada. Por favor, inicie sesión nuevamente.')
            return redirect('accounts:login')

        conjuntos_usuario = ConjuntoResidencial.objects.filter(
            usuario__cedula=cedula,
            usuario__is_active=True,
            estado=True
        ).distinct()

        form = SelectConjuntoForm(conjuntos=conjuntos_usuario, data=request.POST)
        if form.is_valid():
            conjunto = form.cleaned_data['conjunto']
            user = Usuario.objects.filter(cedula=cedula, conjunto=conjunto, is_active=True).first()
            if user:
                user.backend = 'accounts.backends.CedulaConjuntoBackend'
                login(request, user)
                request.session.pop('login_cedula', None)
                request.session.pop('login_token', None)
                return self._redirect_by_user_type(user)
            else:
                messages.error(request, 'Error al autenticar. Credenciales inválidas.')
                return redirect('accounts:login')

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
        return redirect('accounts:login')

    def get_next_page(self):
        return 'login'


class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/reset_password.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')

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


class CustomPasswordChangeView(LoginRequiredMixin, View):
    login_url = '/accounts/login/'

    def get(self, request, *args, **kwargs):
        form = CustomSetPasswordForm(user=request.user)
        return render(request, 'accounts/cambiar_password.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = CustomSetPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Tu contraseña ha sido cambiada con éxito.')
            return redirect('kislevsmart:dashboard')
        messages.error(request, 'Por favor, corrige los errores.')
        return render(request, 'accounts/cambiar_password.html', {'form': form})


class RecuperarPasswordView(View):
    """Recuperar contraseña por cédula, sin necesidad de email."""

    def get(self, request):
        paso = request.session.get('recuperar_paso', 1)
        return render(request, 'accounts/recuperar_password.html', {'paso': paso})

    def post(self, request):
        paso = request.session.get('recuperar_paso', 1)

        if paso == 1:
            cedula = request.POST.get('cedula', '').strip()
            usuario = Usuario.objects.filter(cedula=cedula, is_active=True).first()
            if not usuario:
                messages.error(request, 'No existe un usuario con esa cédula.')
                return render(request, 'accounts/recuperar_password.html', {'paso': 1})
            request.session['recuperar_user_id'] = usuario.pk
            request.session['recuperar_paso'] = 2
            return render(request, 'accounts/recuperar_password.html', {'paso': 2, 'nombre': usuario.nombre})

        if paso == 2:
            user_id = request.session.get('recuperar_user_id')
            try:
                usuario = Usuario.objects.get(pk=user_id)
            except Usuario.DoesNotExist:
                request.session.pop('recuperar_paso', None)
                request.session.pop('recuperar_user_id', None)
                messages.error(request, 'Sesión expirada. Intenta de nuevo.')
                return redirect('accounts:recuperar_password')

            p1 = request.POST.get('password1', '')
            p2 = request.POST.get('password2', '')
            if len(p1) < 8:
                messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
                return render(request, 'accounts/recuperar_password.html', {'paso': 2, 'nombre': usuario.nombre})
            if p1 != p2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return render(request, 'accounts/recuperar_password.html', {'paso': 2, 'nombre': usuario.nombre})

            usuario.set_password(p1)
            usuario.save()
            request.session.pop('recuperar_paso', None)
            request.session.pop('recuperar_user_id', None)
            messages.success(request, 'Contraseña actualizada. Ya puedes iniciar sesión.')
            return redirect('accounts:login')

        return redirect('accounts:recuperar_password')


class PasswordResetDoneView(TemplateView):
    template_name = 'accounts/password_reset_done.html'