# accounts/views.py
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
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
        if user.is_saas_owner:
            return redirect('accounts:saas_dashboard')
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
        if user.is_saas_owner:
            return redirect('accounts:saas_dashboard')
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
        import threading
        email = form.cleaned_data['email']
        if not Usuario.objects.filter(email=email).exists():
            messages.error(self.request, 'No hay una cuenta asociada a ese correo electrónico.')
            return self.form_invalid(form)

        # Enviar email en hilo separado para no bloquear el worker
        def send_reset_email():
            import logging
            logger = logging.getLogger(__name__)
            try:
                form.save(
                    request=self.request,
                    use_https=self.request.is_secure(),
                    from_email=None,
                    email_template_name=self.email_template_name,
                    subject_template_name=self.subject_template_name,
                    html_email_template_name=self.html_email_template_name,
                    extra_email_context=self.extra_email_context,
                )
                logger.info("Email de reset enviado correctamente")
            except Exception as e:
                logger.error(f"Error enviando email de reset: {e}")

        threading.Thread(target=send_reset_email, daemon=True).start()
        messages.success(self.request, 'Se ha enviado un enlace para restablecer la contraseña al correo electrónico mencionado.')
        from django.shortcuts import redirect
        return redirect(self.success_url)


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
            return redirect('dashboard')
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


# ── Force password change ────────────────────────────────────────────────────

class ForcePasswordChangeView(LoginRequiredMixin, View):
    """Intercept login when must_change_password=True."""
    login_url = '/accounts/login/'

    def get(self, request):
        form = CustomSetPasswordForm(user=request.user)
        return render(request, 'accounts/force_password_change.html', {'form': form})

    def post(self, request):
        form = CustomSetPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            request.user.must_change_password = False
            request.user.save(update_fields=['must_change_password'])
            messages.success(request, 'Contraseña actualizada. Bienvenido.')
            redirects = {
                'propietario': 'accounts:visor_propietario',
                'administrador': 'accounts:visor_admin',
                'porteria': 'accounts:control_porteria',
            }
            return redirect(redirects.get(request.user.user_type, 'accounts:login'))
        return render(request, 'accounts/force_password_change.html', {'form': form})


# ── SaaS owner dashboard ─────────────────────────────────────────────────────

def saas_required(view_func):
    """Decorator: only allows is_saas_owner users."""
    from functools import wraps
    from django.http import HttpResponseForbidden

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_saas_owner:
            return HttpResponseForbidden('Acceso restringido al propietario del SaaS.')
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@saas_required
def saas_dashboard(request):
    """Super-admin dashboard: list of all residential complexes + global send metrics."""
    from kislevsmart.models import LogEnvio, ConfigGlobal
    from django.utils import timezone
    from django.db.models import Count
    import datetime

    conjuntos = ConjuntoResidencial.objects.all().order_by('nombre')
    stats = []
    for c in conjuntos:
        stats.append({
            'conjunto': c,
            'propietarios': Usuario.objects.filter(conjunto=c, user_type='propietario', is_active=True).count(),
            'admins': Usuario.objects.filter(conjunto=c, user_type='administrador', is_active=True).count(),
            'porteria': Usuario.objects.filter(conjunto=c, user_type='porteria', is_active=True).count(),
        })

    # ── Métricas globales del mes actual ──────────────────────────────────────
    hoy = timezone.localdate()
    mes_inicio = hoy.replace(day=1)
    cfg = ConfigGlobal.get()

    emails_mes   = LogEnvio.objects.filter(tipo='email',     fecha__date__gte=mes_inicio).count()
    wa_mes       = LogEnvio.objects.filter(tipo='whatsapp',  fecha__date__gte=mes_inicio).count()

    # Ranking top 5 conjuntos por emails y por whatsapp este mes
    top_email = (
        LogEnvio.objects
        .filter(tipo='email', fecha__date__gte=mes_inicio, conjunto__isnull=False)
        .values('conjunto__nombre')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )
    top_wa = (
        LogEnvio.objects
        .filter(tipo='whatsapp', fecha__date__gte=mes_inicio, conjunto__isnull=False)
        .values('conjunto__nombre')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    pct_email = min(round(emails_mes * 100 / cfg.limite_emails_mes) if cfg.limite_emails_mes else 0, 100)
    pct_wa    = min(round(wa_mes    * 100 / cfg.limite_whatsapp_mes) if cfg.limite_whatsapp_mes else 0, 100)

    return render(request, 'accounts/saas_dashboard.html', {
        'stats':           stats,
        'emails_mes':      emails_mes,
        'wa_mes':          wa_mes,
        'limite_emails':   cfg.limite_emails_mes,
        'limite_wa':       cfg.limite_whatsapp_mes,
        'pct_email':       pct_email,
        'pct_wa':          pct_wa,
        'top_email':       list(top_email),
        'top_wa':          list(top_wa),
        'mes_label':       hoy.strftime('%B %Y'),
    })


@login_required
@saas_required
def gestionar_conjunto(request, conjunto_id):
    """Panel hub por conjunto para el SaaS owner."""
    from django.utils import timezone
    from django.db.models import Count, Max
    import datetime

    conjunto = get_object_or_404(ConjuntoResidencial, pk=conjunto_id)

    # ── Filtro de fechas ──────────────────────────────────────────────────────
    hoy = timezone.localdate()
    fecha_desde_str = request.GET.get('desde', '')
    fecha_hasta_str = request.GET.get('hasta', '')
    try:
        fecha_desde = datetime.date.fromisoformat(fecha_desde_str)
    except ValueError:
        fecha_desde = hoy.replace(day=1)
    try:
        fecha_hasta = datetime.date.fromisoformat(fecha_hasta_str)
    except ValueError:
        fecha_hasta = hoy

    # ── Métricas de envíos (requiere migración 0019) ──────────────────────────
    emails_periodo = 0
    wa_periodo     = 0
    pct_email      = 0
    pct_wa         = 0
    historico      = []
    ultimos_envios = []
    limite_emails  = 1000
    limite_wa      = 500
    try:
        from kislevsmart.models import LogEnvio, ConfigGlobal
        qs_envios = LogEnvio.objects.filter(
            conjunto=conjunto,
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta,
        )
        emails_periodo = qs_envios.filter(tipo='email').count()
        wa_periodo     = qs_envios.filter(tipo='whatsapp').count()

        cfg = ConfigGlobal.get()
        limite_emails = cfg.limite_emails_mes
        limite_wa     = cfg.limite_whatsapp_mes
        pct_email = min(round(emails_periodo * 100 / limite_emails) if limite_emails else 0, 100)
        pct_wa    = min(round(wa_periodo    * 100 / limite_wa)     if limite_wa     else 0, 100)

        for i in range(5, -1, -1):
            d = (hoy.replace(day=1) - datetime.timedelta(days=i * 28)).replace(day=1)
            if d.month < 12:
                fin = d.replace(month=d.month + 1, day=1) - datetime.timedelta(days=1)
            else:
                fin = d.replace(month=12, day=31)
            historico.append({
                'label':    d.strftime('%b %Y'),
                'emails':   LogEnvio.objects.filter(conjunto=conjunto, tipo='email',    fecha__date__gte=d, fecha__date__lte=fin).count(),
                'whatsapp': LogEnvio.objects.filter(conjunto=conjunto, tipo='whatsapp', fecha__date__gte=d, fecha__date__lte=fin).count(),
            })

        ultimos_envios = list(LogEnvio.objects.filter(conjunto=conjunto).order_by('-fecha')[:20])
    except Exception:
        pass

    # ── Residentes ────────────────────────────────────────────────────────────
    total_res   = Usuario.objects.filter(conjunto=conjunto).count()
    activos_res = Usuario.objects.filter(conjunto=conjunto, is_active=True).count()

    # ── Actividad general ─────────────────────────────────────────────────────
    visitantes_mes = 0
    paq_pendientes = 0
    try:
        from kislevsmart.models import Visitante
        visitantes_mes = Visitante.objects.filter(
            conjunto=conjunto,
            fecha_generacion__date__gte=hoy.replace(day=1),
        ).count()
    except Exception:
        pass
    try:
        from kislevsmart.models import Paquete
        paq_pendientes = Paquete.objects.filter(conjunto=conjunto, estado='pendiente').count()
    except Exception:
        pass
    ultimo_login = Usuario.objects.filter(conjunto=conjunto, last_login__isnull=False).aggregate(
        ult=Max('last_login')
    )['ult']

    return render(request, 'accounts/gestionar_conjunto.html', {
        'conjunto':        conjunto,
        'fecha_desde':     fecha_desde.isoformat(),
        'fecha_hasta':     fecha_hasta.isoformat(),
        'emails_periodo':  emails_periodo,
        'wa_periodo':      wa_periodo,
        'limite_emails':   cfg.limite_emails_mes,
        'limite_wa':       cfg.limite_whatsapp_mes,
        'pct_email':       pct_email,
        'pct_wa':          pct_wa,
        'historico':       historico,
        'ultimos_envios':  ultimos_envios,
        'total_res':       total_res,
        'activos_res':     activos_res,
        'visitantes_mes':  visitantes_mes,
        'paq_pendientes':  paq_pendientes,
        'ultimo_login':    ultimo_login,
    })


@login_required
@saas_required
def update_config_global(request):
    """AJAX — actualiza los límites globales de SES/Twilio."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    from kislevsmart.models import ConfigGlobal
    cfg = ConfigGlobal.get()
    try:
        cfg.limite_emails_mes   = int(request.POST.get('limite_emails_mes', cfg.limite_emails_mes))
        cfg.limite_whatsapp_mes = int(request.POST.get('limite_whatsapp_mes', cfg.limite_whatsapp_mes))
        cfg.save()
        return JsonResponse({'ok': True})
    except (ValueError, TypeError) as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)


# ── Excel template download ──────────────────────────────────────────────────

@login_required
@saas_required
def download_template(request):
    """Generate and return the Excel onboarding template."""
    import io
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        from django.http import HttpResponse
        return HttpResponse('openpyxl no instalado.', status=500)

    from django.http import HttpResponse

    wb = openpyxl.Workbook()

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(fill_type='solid', fgColor='4F2984')
    center = Alignment(horizontal='center', vertical='center')

    def make_sheet(wb, title, headers, example_row=None, first=False):
        ws = wb.active if first else wb.create_sheet(title=title)
        if first:
            ws.title = title
        ws.row_dimensions[1].height = 22
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            ws.column_dimensions[get_column_letter(col_idx)].width = max(len(header) + 4, 18)
        if example_row:
            for col_idx, val in enumerate(example_row, start=1):
                ws.cell(row=2, column=col_idx, value=val)
        return ws

    # Sheet 1: Conjunto
    make_sheet(wb, 'Conjunto',
               ['campo', 'valor', 'opciones_validas'],
               first=True)
    ws_c = wb['Conjunto']
    fields = [
        ('nombre',             'Conjunto Residencial El Prado', ''),
        ('nit',                '900123456-7',                   ''),
        ('direccion',          'Cra 15 # 80-20, Bogotá',        ''),
        ('telefono',           '3001234567',                    ''),
        ('email_contacto',     'admin@elprado.com',             ''),
        ('link_pago',          'https://pagos.ejemplo.com/elprado', ''),
        ('tipo_distribucion',  'torre_apto',
         'torre_apto | interior_apto | bloque_apto | manzana_casa | solo_apto | solo_casa'),
    ]
    # Estilo especial para columna de opciones
    from openpyxl.styles import Font as _Font, PatternFill as _Fill, Alignment as _Align
    note_font = _Font(italic=True, color='888888', size=9)
    for i, row_vals in enumerate(fields, start=2):
        ws_c.cell(row=i, column=1, value=row_vals[0])
        ws_c.cell(row=i, column=2, value=row_vals[1])
        if row_vals[2]:
            cell = ws_c.cell(row=i, column=3, value=row_vals[2])
            cell.font = note_font
    ws_c.column_dimensions['C'].width = 70

    # Sheet 2: Agrupaciones (Torres / Interiores / Bloques / Manzanas)
    make_sheet(wb, 'Agrupaciones',
               ['nombre', 'numero_pisos', 'aptos_por_piso'],
               example_row=['Torre 1', 5, 4])
    # Nota en celda A1
    ws_ag = wb['Agrupaciones']
    ws_ag['A1'].comment = None
    note_row = ws_ag.cell(row=ws_ag.max_row + 2, column=1,
                          value='💡 Usa el nombre que corresponda al tipo_distribucion: Torre 1, Interior A, Bloque 3, Manzana 5, etc.')
    note_row.font = note_font

    # Sheet 3: Administrador
    make_sheet(wb, 'Administrador',
               ['cedula', 'nombre', 'email', 'telefono'],
               example_row=['1020304050', 'Carlos Gómez', 'carlos@elprado.com', '3109876543'])

    # Sheet 4: Propietarios
    make_sheet(wb, 'Propietarios',
               ['cedula', 'nombre', 'email', 'telefono', 'agrupacion', 'unidad'],
               example_row=['52987654', 'María López', 'maria@gmail.com', '3151234567', 'Torre 1', '0101'])
    ws_p = wb['Propietarios']
    ws_p.cell(row=1, column=5).comment = None
    note_p = ws_p.cell(row=ws_p.max_row + 2, column=1,
                       value='💡 "agrupacion" = nombre de la Torre/Interior/Bloque/Manzana. Déjalo vacío si el conjunto no usa agrupaciones.')
    note_p.font = note_font

    # Sheet 5: Portería
    make_sheet(wb, 'Portería',
               ['cedula', 'nombre', 'email', 'telefono'],
               example_row=['80654321', 'Pedro Ramos', 'pedro@elprado.com', '3204567890'])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_conjunto.xlsx"'
    return response


# ── Upload / import conjunto via web ────────────────────────────────────────

@login_required
@saas_required
def upload_conjunto(request):
    """Web UI to upload the Excel file and import a new conjunto."""
    if request.method == 'GET':
        return render(request, 'accounts/upload_conjunto.html')

    excel_file = request.FILES.get('excel')
    send_emails = request.POST.get('send_emails') == 'on'
    tipo_dist_form = request.POST.get('tipo_distribucion', 'torre_apto')

    if not excel_file:
        messages.error(request, 'Debes adjuntar un archivo Excel.')
        return render(request, 'accounts/upload_conjunto.html')

    if not excel_file.name.endswith('.xlsx'):
        messages.error(request, 'Solo se aceptan archivos .xlsx')
        return render(request, 'accounts/upload_conjunto.html')

    import io
    import secrets
    import string

    try:
        import openpyxl
    except ImportError:
        messages.error(request, 'openpyxl no está instalado en el servidor.')
        return render(request, 'accounts/upload_conjunto.html')

    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    def _random_password(length=12):
        alphabet = string.ascii_letters + string.digits + '!@#$%'
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _send_welcome(email, nombre, conjunto_nombre, cedula, password):
        try:
            context = {
                'nombre': nombre,
                'conjunto_nombre': conjunto_nombre,
                'cedula': cedula,
                'password': password,
                'login_url': getattr(settings, 'SITE_URL', 'https://kislev.net.co') + '/accounts/login/',
            }
            html = render_to_string('emails/bienvenida_credenciales.html', context)
            text = (
                f"Hola {nombre},\n\nBienvenido a {conjunto_nombre} en KislevSmart.\n\n"
                f"Usuario: {cedula}\nContraseña temporal: {password}\n\n"
                f"Cámbiala en tu primer inicio de sesión.\n{context['login_url']}"
            )
            msg = EmailMultiAlternatives(
                subject=f'Bienvenido a KislevSmart — {conjunto_nombre}',
                body=text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )
            msg.attach_alternative(html, 'text/html')
            msg.send(fail_silently=False)
            try:
                from kislevsmart.utils import log_envio as _log_envio
                from accounts.models import ConjuntoResidencial as _CR
                _conj = _CR.objects.filter(nombre=conjunto_nombre).first()
                _log_envio('email', conjunto=_conj, detalle=f'Bienvenida: {nombre}')
            except Exception:
                pass
            return True
        except Exception as exc:
            return str(exc)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(excel_file.read()), data_only=True)
    except Exception as exc:
        messages.error(request, f'No se pudo leer el Excel: {exc}')
        return render(request, 'accounts/upload_conjunto.html')

    try:
        ws_c = wb['Conjunto']
        data = {row[0].value: row[1].value for row in ws_c.iter_rows(min_row=2) if row[0].value}

        for field in ('nombre', 'nit', 'direccion'):
            if not data.get(field):
                raise ValueError(f'Hoja "Conjunto": falta el campo "{field}"')

        # tipo_distribucion: primero del Excel, luego del form web
        tipo_dist = str(data.get('tipo_distribucion', '') or tipo_dist_form or 'torre_apto').strip()
        valid_tipos = [c[0] for c in ConjuntoResidencial.DISTRIBUCION_CHOICES]
        if tipo_dist not in valid_tipos:
            tipo_dist = 'torre_apto'

        conjunto, _ = ConjuntoResidencial.objects.get_or_create(
            nit=str(data['nit']).strip(),
            defaults={
                'nombre': str(data['nombre']).strip(),
                'direccion': str(data.get('direccion', '')).strip(),
                'telefono': str(data.get('telefono', '') or ''),
                'email_contacto': str(data.get('email_contacto', '') or '') or None,
                'link_pago': str(data.get('link_pago', '') or '') or None,
                'tipo_distribucion': tipo_dist,
            },
        )

        # Agrupaciones — soporta hoja "Agrupaciones" (nueva) y "Torres" (antigua)
        torres_map = {}
        sheet_name = 'Agrupaciones' if 'Agrupaciones' in wb.sheetnames else 'Torres'
        ws_torres = wb[sheet_name]
        headers = [c.value for c in next(ws_torres.iter_rows(min_row=1, max_row=1))]
        for row in ws_torres.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            rd = dict(zip(headers, row))
            nombre_torre = str(rd.get('nombre', '')).strip()
            if not nombre_torre:
                continue
            from accounts.models import Torre
            torre, _ = Torre.objects.get_or_create(
                conjunto=conjunto,
                nombre=nombre_torre,
                defaults={
                    'numero_pisos': int(rd.get('numero_pisos') or 1),
                    'aptos_por_piso': int(rd.get('aptos_por_piso') or 4),
                },
            )
            torres_map[nombre_torre] = torre

        created_count = 0
        skipped_count = 0
        email_errors = []

        def create_user(row_data, user_type):
            nonlocal created_count, skipped_count
            cedula = str(row_data.get('cedula', '') or '').strip()
            nombre = str(row_data.get('nombre', '') or '').strip()
            email = str(row_data.get('email', '') or '').strip()
            if not cedula or not nombre or not email:
                skipped_count += 1
                return
            if Usuario.objects.filter(cedula=cedula, conjunto=conjunto).exists():
                skipped_count += 1
                return
            password = _random_password()
            # Soporta columnas nuevas (agrupacion/unidad) y antiguas (torre/apartamento)
            torre_nombre = str(row_data.get('agrupacion', '') or row_data.get('torre', '') or '').strip()
            torre_obj = torres_map.get(torre_nombre)
            apartamento = str(row_data.get('unidad', '') or row_data.get('apartamento', '') or '').strip()
            usuario = Usuario.objects.create_user(
                cedula=cedula,
                nombre=nombre,
                email=email,
                password=password,
                conjunto=conjunto,
                user_type=user_type,
                phone_number=str(row_data.get('telefono', '') or ''),
                torre=torre_obj,
                apartamento=apartamento,
                must_change_password=True,
            )
            created_count += 1
            if send_emails:
                result = _send_welcome(email, nombre, conjunto.nombre, cedula, password)
                if result is not True:
                    email_errors.append(f'{email}: {result}')

        for sheet, utype in [('Administrador', 'administrador'), ('Propietarios', 'propietario'), ('Portería', 'porteria')]:
            ws_s = wb[sheet]
            hdrs = [c.value for c in next(ws_s.iter_rows(min_row=1, max_row=1))]
            for row in ws_s.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                create_user(dict(zip(hdrs, row)), utype)

    except ValueError as exc:
        messages.error(request, str(exc))
        return render(request, 'accounts/upload_conjunto.html')
    except Exception as exc:
        messages.error(request, f'Error durante la importación: {exc}')
        return render(request, 'accounts/upload_conjunto.html')

    success_msg = f'Conjunto "{conjunto.nombre}" importado: {created_count} usuarios creados, {skipped_count} omitidos.'
    if email_errors:
        success_msg += f' ({len(email_errors)} errores de email)'
    messages.success(request, success_msg)
    return redirect('accounts:saas_dashboard')


# ── Gestión de usuarios (admin panel) ───────────────────────────────────────

from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json

@login_required
def gestion_usuarios(request):
    """Panel de gestión de residentes para administradores (y saas_owner con ?conjunto=id)."""
    user = request.user

    if user.is_saas_owner and request.GET.get('conjunto'):
        try:
            conjunto = ConjuntoResidencial.objects.get(pk=request.GET['conjunto'])
        except ConjuntoResidencial.DoesNotExist:
            conjunto = user.conjunto
    elif user.user_type == 'administrador' or user.is_saas_owner:
        conjunto = user.conjunto
    else:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from accounts.models import Torre
    torres = Torre.objects.filter(conjunto=conjunto, activo=True).order_by('nombre')

    torre_id = request.GET.get('torre')
    user_type_filter = request.GET.get('tipo', '')
    search = request.GET.get('q', '').strip()
    estado_filter = request.GET.get('estado', '')

    usuarios_qs = Usuario.objects.filter(conjunto=conjunto).exclude(is_saas_owner=True).order_by('torre__nombre', 'apartamento', 'nombre')

    if torre_id:
        usuarios_qs = usuarios_qs.filter(torre_id=torre_id)
    if user_type_filter:
        usuarios_qs = usuarios_qs.filter(user_type=user_type_filter)
    if search:
        from django.db.models import Q
        usuarios_qs = usuarios_qs.filter(Q(nombre__icontains=search) | Q(cedula__icontains=search) | Q(apartamento__icontains=search))
    if estado_filter == 'activo':
        usuarios_qs = usuarios_qs.filter(is_active=True)
    elif estado_filter == 'inactivo':
        usuarios_qs = usuarios_qs.filter(is_active=False)

    context = {
        'conjunto': conjunto,
        'torres': torres,
        'usuarios': usuarios_qs,
        'torre_id': torre_id,
        'user_type_filter': user_type_filter,
        'search': search,
        'estado_filter': estado_filter,
        'total': usuarios_qs.count(),
        'is_saas_owner': user.is_saas_owner,
        'all_conjuntos': ConjuntoResidencial.objects.all() if user.is_saas_owner else None,
    }
    return render(request, 'accounts/gestion_usuarios.html', context)


@require_POST
@login_required
def toggle_usuario_activo(request, usuario_id):
    """AJAX: activa o desactiva un usuario."""
    if request.user.user_type not in ('administrador',) and not request.user.is_saas_owner:
        return JsonResponse({'error': 'Sin permiso'}, status=403)
    try:
        target = Usuario.objects.get(pk=usuario_id)
    except Usuario.DoesNotExist:
        return JsonResponse({'error': 'No encontrado'}, status=404)
    if not request.user.is_saas_owner and target.conjunto != request.user.conjunto:
        return JsonResponse({'error': 'Sin permiso'}, status=403)
    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    return JsonResponse({'is_active': target.is_active})


@require_POST
@login_required
def editar_usuario(request, usuario_id):
    """AJAX: edita torre, apartamento, teléfono y tipo de un usuario."""
    if request.user.user_type not in ('administrador',) and not request.user.is_saas_owner:
        return JsonResponse({'error': 'Sin permiso'}, status=403)
    try:
        target = Usuario.objects.get(pk=usuario_id)
    except Usuario.DoesNotExist:
        return JsonResponse({'error': 'No encontrado'}, status=404)
    if not request.user.is_saas_owner and target.conjunto != request.user.conjunto:
        return JsonResponse({'error': 'Sin permiso'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    from accounts.models import Torre
    fields_updated = []

    if 'torre_id' in data:
        if data['torre_id']:
            try:
                torre = Torre.objects.get(pk=data['torre_id'], conjunto=target.conjunto)
                target.torre = torre
            except Torre.DoesNotExist:
                return JsonResponse({'error': 'Torre no válida'}, status=400)
        else:
            target.torre = None
        fields_updated.append('torre')

    if 'apartamento' in data:
        target.apartamento = str(data['apartamento']).strip()[:10]
        fields_updated.append('apartamento')

    if 'phone_number' in data:
        target.phone_number = str(data['phone_number']).strip()[:15]
        fields_updated.append('phone_number')

    if 'user_type' in data and data['user_type'] in ('propietario', 'administrador', 'porteria'):
        target.user_type = data['user_type']
        fields_updated.append('user_type')

    if 'email' in data:
        email_val = str(data['email']).strip()[:254]
        if email_val:
            target.email = email_val
            fields_updated.append('email')

    if fields_updated:
        target.save(update_fields=fields_updated)

    return JsonResponse({
        'ok': True,
        'torre': target.torre.nombre if target.torre else '',
        'apartamento': target.apartamento,
        'phone_number': target.phone_number or '',
        'user_type': target.user_type,
        'email': target.email or '',
    })


@login_required
def exportar_usuarios_excel(request):
    """Descarga la lista de usuarios del conjunto en Excel."""
    if request.user.user_type not in ('administrador',) and not request.user.is_saas_owner:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.user.is_saas_owner and request.GET.get('conjunto'):
        try:
            conjunto = ConjuntoResidencial.objects.get(pk=request.GET['conjunto'])
        except ConjuntoResidencial.DoesNotExist:
            conjunto = request.user.conjunto
    else:
        conjunto = request.user.conjunto

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        from django.http import HttpResponse
        return HttpResponse('openpyxl no instalado', status=500)

    import io
    from django.http import HttpResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Residentes'

    headers = ['Nombre', 'Cédula', 'Email', 'Teléfono', 'Torre', 'Apartamento', 'Tipo', 'Estado']
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(fill_type='solid', fgColor='4F2984')
    center = Alignment(horizontal='center')

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(h) + 4, 16)

    usuarios = Usuario.objects.filter(conjunto=conjunto).exclude(is_saas_owner=True).order_by('torre__nombre', 'apartamento', 'nombre')
    for row_idx, u in enumerate(usuarios, start=2):
        ws.cell(row=row_idx, column=1, value=u.nombre)
        ws.cell(row=row_idx, column=2, value=u.cedula)
        ws.cell(row=row_idx, column=3, value=u.email)
        ws.cell(row=row_idx, column=4, value=u.phone_number or '')
        ws.cell(row=row_idx, column=5, value=u.torre.nombre if u.torre else '')
        ws.cell(row=row_idx, column=6, value=u.apartamento)
        ws.cell(row=row_idx, column=7, value=u.get_user_type_display())
        ws.cell(row=row_idx, column=8, value='Activo' if u.is_active else 'Inactivo')

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="residentes_{conjunto.nit}.xlsx"'
    return response