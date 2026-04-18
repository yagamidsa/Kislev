---
name: Kislev
description: |
  Guía maestra para desarrollar Kislev (sistema de gestión residencial Django) usando Claude Code
  con arquitectura multi-agente. Úsala siempre que vayas a implementar nuevas features, refactorizar
  módulos existentes, o coordinar trabajo entre agentes especializados en el proyecto.
---

# Kislev — Claude Code Multi-Agent SKILL

## Estado actual del proyecto

```
kislevsmart/          ← app principal
  models.py           ← Visitante, VisitanteVehicular, Sala, Reserva,
                         ParqueaderoCarro, ParqueaderoMoto,
                         Cuota, Pago, AuditLog,
                         Novedad, ArchivoNovedad, ComentarioNovedad, LikeNovedad ← NUEVOS
  views.py            ← ~2200 líneas (pendiente dividir en módulos)
  urls.py
  utils.py            ← role_required (reexporta de accounts), log_audit
accounts/             ← auth, ConjuntoResidencial, Torre, Usuario
  models.py
  views.py            ← incluye CustomPasswordChangeView + RecuperarPasswordView
  backends.py
  utils.py            ← role_required (fuente canónica)
```

**Stack:** Django 5.1 + Python 3.13 · PostgreSQL 18 (puerto 5433) · Railway (deploy) · Redis (cache/sesiones) · **Resend vía django-anymail** (email HTTP API — Railway bloquea SMTP) · Whitenoise · django-ratelimit

**Dominio:** kislev.net.co · **Moneda:** COP (pesos colombianos) · **TZ:** America/Bogota

**PC actual:** Lenovo / usuario Windows: Lenovo (antes era AlipioD — rutas antiguas inválidas)

**Nombre de la app:** Solo **Kislev** — nunca escribir "KislevSmart" en ningún template, vista, email ni texto visible al usuario.

**⚠️ REGLA CRÍTICA — RESPONSIVE SIEMPRE:** Los usuarios (porteros, propietarios) usan principalmente celular. Toda vista nueva o modificada DEBE tener `@media(max-width:600px)` con breakpoints para topbar, container, cards, tablas y formularios.

**⚠️ REGLA CRÍTICA — SCROLL EN iOS SIEMPRE:** Cualquier pantalla que use el patrón `html,body { overflow:hidden }` + `.scroll-root` DEBE tener exactamente:
```css
html { height: -webkit-fill-available; }
.scroll-root {
  height: 100vh;
  height: 100dvh;                    /* dvh = dynamic — se actualiza con URL bar de Safari */
  height: -webkit-fill-available;    /* fallback iOS < 15.4 */
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
}
```
Sin `dvh`, en iOS el scroll queda corto porque Safari calcula `100vh` con la URL bar visible y al ocultarse al hacer scroll el contenedor no se actualiza.

---

## Arquitectura multi-agente — cómo dividir el trabajo

Cuando una tarea es grande, lanza sub-agentes con `claude --dangerously-skip-permissions -p "<prompt>"`.  
Cada agente recibe **solo el contexto que necesita** para minimizar tokens.

### Plantillas de agentes disponibles

---

### 🔵 AGENTE: Modelo de datos
```
Eres un agente Django especializado en modelos y migraciones para Kislev.
Contexto del proyecto:
- App: kislevsmart + accounts
- DB: PostgreSQL 18 en Railway (local: puerto 5433)
- Modelos existentes: ConjuntoResidencial, Torre, Usuario(AbstractBaseUser),
  Visitante, VisitanteVehicular, Sala(con FK conjunto), Reserva,
  ParqueaderoCarro, ParqueaderoMoto, Cuota, Pago, AuditLog,
  Novedad, ArchivoNovedad, ComentarioNovedad, LikeNovedad

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Solo toca models.py y migrations/
- Genera siempre la migración con makemigrations --name descriptivo
- No rompas unique_together existentes
- Usa JSONField nativo de Django (no postgres)
- Documenta cada campo nuevo con help_text
```

---

### 🟢 AGENTE: Vistas y API
```
Eres un agente Django especializado en views/APIs para Kislev.
Contexto:
- views.py tiene ~2200 líneas — NO lo reescribas completo, solo añade/edita funciones
- Auth: login_required + verificación de user_type ('administrador','propietario','porteria')
- Email: usar EmailMultiAlternatives con fail_silently=True (SES local no configurado)
- Redis: django.core.cache (default cache)
- Patrón existente: JsonResponse para APIs, render() para vistas
- AuditLog: usar log_audit(request, accion, detalle) de kislevsmart.utils

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Añade imports solo si son nuevos
- Registra la URL nueva en urls.py
- Devuelve {'status':'ok'|'error', 'message':...} en todas las APIs JSON
- Sanitiza inputs con sanitize_text() que ya existe
- Llama log_audit() en acciones críticas (crear, validar, pagar)
```

---

### 🟡 AGENTE: Frontend / Templates
```
Eres un agente de frontend para Kislev (Django templates, CSS inline).
Contexto:
- Templates en kislevsmart/templates/ y accounts/templates/
- Estáticos en kislevsmart/static/ y accounts/static/
- UI en español, mercado colombiano
- Estilo: fondo dark gradient (135deg, #1a1a2e, #16213e, #0f3460), acento #e100ff/#7f00ff
- Existen: dashboard, portería QR, salas, notificaciones, parking,
           historial visitantes (propietario), finanzas (admin + propietario),
           novedades (lista, detalle, crear, metricas)

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Formularios con csrf_token siempre
- OBLIGATORIO responsive: incluir @media(max-width:600px) en TODA vista nueva
  → topbar flex-wrap:wrap, container padding reducido, cards sin hover transform,
    tablas con overflow-x:auto y min-width:500px, formularios full width
- Porteros y propietarios usan celular → mobile-first es prioridad #1
- Mensajes de éxito/error con el sistema de messages de Django
- No usar frameworks externos (Bootstrap, Tailwind) — CSS inline/style block
```

---

### 🔴 AGENTE: Infraestructura / DevOps
```
Eres un agente de infraestructura para Kislev en Railway.
Contexto:
- Deploy: Railway (bloquea puertos SMTP 465 y 587 — NUNCA usar SMTP)
- Email: Resend vía django-anymail HTTP API (variable RESEND_API_KEY en Railway)
  → EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
  → Plan gratuito: 3,000/mes · 100/día | Plan Pro ($20 USD): 50,000/mes
- Variables de entorno en Railway: DATABASE_URL, RESEND_API_KEY,
  DEFAULT_FROM_EMAIL, DJANGO_SECRET_KEY, REDIS_URL, FERNET_KEY
- Estáticos: Whitenoise + CompressedManifestStaticFilesStorage
- Rate limiting: RATELIMIT_ENABLED=not DEBUG (requiere Redis en prod)

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Nunca hardcodees credenciales
- Usa os.environ.get() con default seguro
- Si cambias settings.py, verifica que no rompa DEBUG=False
- Para Redis: django-redis con CACHE_BACKEND url
- Email en dev (DEBUG=True sin RESEND_API_KEY): console backend
- Email en prod sin RESEND_API_KEY: dummy backend (no lanza error)
```

---

## BACKLOG — Estado actualizado al 2026-04-18

### ✅ COMPLETADO sesiones anteriores

| Item | Descripción |
|------|-------------|
| C1 | Fernet hardcodeada → variable de entorno FERNET_KEY |
| C2 | Password en sesión → signing.dumps() token firmado |
| C3 | DJANGO_SECRET_KEY sin default inseguro |
| C4 | DEBUG=False por defecto |
| D1 | usuario_id bug → FK a ConjuntoResidencial con db_column='usuario_id' |
| D2 | Reservas con select_for_update (race condition) |
| D3 | email_creador = request.user.email |
| R1 | Procfile con release + gunicorn configurado para Railway |
| R2 | conn_max_age=60 + conn_health_checks=True |
| R3 | Cache Redis (django_redis) en prod, LocMemCache en dev |
| R4 | ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS con kislev.net.co |
| R5 | Logging solo a consola (Railway filesystem efímero) |
| A1 | Rate limiting login: 5/min por IP (django-ratelimit) |
| A2 | QR en BytesIO sin tocar disco |
| A3 | role_required unificado — kislevsmart/utils.py reexporta de accounts |
| A4 | select_related en parqueaderos (N+1) |
| T3 | ConjuntoResidencial hardcodeado → .first() con validación |
| T4 | print() → logger.debug() en modelos |
| T5 | .env.example creado y documentado |
| F2 | Historial visitantes por apartamento (vista propietario) |
| F7 | AuditLog — modelo + helper log_audit() + llamadas en views críticas |
| F1 | Módulo financiero: Cuota + Pago + EstadoCuenta (admin + propietario) |
| F8 | Dashboard financiero — KPIs recaudo, gráfico Chart.js, barra progreso |
| F5 | Reporte PDF mensual con WeasyPrint (visitantes, reservas, pagos) |
| F9 | Tests pytest-django — 20/20 (auth, visitantes, reservas, finanzas) |
| "Recuérdame" | Checkbox en login con session.set_expiry(30 días) |

### ✅ COMPLETADO sesiones 2026-04-03 a 2026-04-18

| Item | Descripción |
|------|-------------|
| T2 | **Django 3.2 → 5.1 + Python 3.7 → 3.13** (completado al migrar al nuevo PC Lenovo) |
| PC-MIG | Migración completa a PC nuevo: nuevo venv, PostgreSQL 18 (puerto 5433), kislev_user grants |
| SEED | Base de datos poblada: 2 conjuntos (Oliva Madrid + Puerto Hayuelos 1), 20 users, salas por conjunto, parqueaderos |
| AUTH-PWD | Módulo cambiar contraseña (logueado): `CustomPasswordChangeView` con `update_session_auth_hash` |
| AUTH-REC | Módulo recuperar contraseña (por cédula, sin email): flujo 2 pasos en sesión. URL: `accounts:recuperar_password` |
| SALA-FK | `Sala.conjunto` FK a ConjuntoResidencial — salas son por conjunto (no compartidas) |
| DROPDOWN | Fix click dropdown en visor_admin/propietario/porteria: `pointer-events:none/auto` + padding en `<a>` en vez de `<li>` |
| SUBTITLE | Panel muestra nombre del conjunto: `{{ user.conjunto.nombre }} (Rol)` en los 3 paneles |
| NOV-MOD | Modelos: `Novedad`, `ArchivoNovedad`, `ComentarioNovedad`, `LikeNovedad` (unique_together novedad+usuario) |
| NOV-VIEWS | Vistas novedades: lista, detalle, crear, eliminar, agregar_comentario, toggle_like (JSON), metricas_novedades |
| NOV-EMAIL | Email HTML al publicar novedad con `EmailMultiAlternatives` + `fail_silently=True` |
| NOV-UI | Templates: lista.html (cards grid), detalle.html (hero img + linkify + like animado), crear.html (preview imagen + multi-file), metricas.html (Chart.js bar+doughnut) |
| NOV-LIKE | Botón ❤️ con animación `heartPop` + `burst` CSS, toggle via fetch POST |
| NOV-RESP | Todos los templates de novedades responsive con `@media(max-width:600px)` |
| MENU-NOV | Menú admin/propietario/porteria actualizado con links a Novedades |
| TIPO-DIST | `tipo_distribucion` enum eliminado → `nombre_agrupacion` (blank=True) + `nombre_unidad` CharField libres. Propiedades: `etiqueta_agrupacion`, `etiqueta_unidad`, `tiene_agrupacion` |
| SAAS-PANEL | Panel SaaS owner en `/accounts/saas/` con métricas globales, lista de conjuntos, toggle activo/inactivo, gestión de usuarios |
| SAAS-UPLOAD | Upload Excel de conjunto con `transaction.atomic()` — todo o nada. Password por defecto: `kislev123`. Errores de email se muestran con detalle |
| SAAS-DELETE | Eliminar conjunto con modal de confirmación + checkbox obligatorio. Endpoint POST `/saas/conjunto/<id>/eliminar/`. CASCADE borra todo |
| QR-SECURITY | Fix seguridad QR: `validar_qr` y `validar_qr_vehicular` filtran por `conjunto_id=request.user.conjunto_id` — QR de un conjunto no válido en otro |
| EMAIL-RESEND | Migrado de AWS SES (denegado producción) a Resend vía django-anymail. Railway bloquea SMTP → solo HTTP API funciona |
| EMAIL-BIENVENIDA | Template `bienvenida_credenciales.html` rediseñado: compatible dark/light mode, estructura 100% tablas, VML para Outlook, `@media prefers-color-scheme` + `[data-ogsc]` |
| SCROLL-IOS | Fix scroll pegado en iOS: `.scroll-root` usa `height:100dvh` + `-webkit-fill-available` + `overscroll-behavior-y:contain`. Aplica en saas_dashboard, gestionar_conjunto, gestion_usuarios |
| NOMBRE-APP | Renombrado "KislevSmart" → "Kislev" en toda la aplicación (templates, views, emails, management commands) |

---

### 🔴 PENDIENTE — Crítico / Alta prioridad

#### [T1] Unificar Visitante + VisitanteVehicular
**Complejidad:** Alta — requiere migración de datos.  
Unificar en un solo modelo con campo `tipo` ('peatonal', 'vehicular') y campos vehiculares opcionales. Dashboard actualmente no incluye visitantes vehiculares en estadísticas.

---

### 🚀 BLOQUE 6 — Features pendientes

| # | Feature | Estado | Complejidad |
|---|---------|--------|-------------|
| F3 | ~~Solicitar SES producción AWS~~ → Resend ya activo | ✅ Completado | — |
| F4 | Notificaciones push PWA | ⏳ Pendiente | Media |
| F6 | API REST con DRF para app móvil | ⏳ Pendiente | Alta |
| F10 | Predicción morosidad con Claude API | ⏳ Pendiente | Alta |

---

### 🏦 BLOQUE 7 — Facturación electrónica (parqueadero)

#### [FE-1] Módulo pago parqueadero + factura electrónica DIAN

**Estado:** ⏳ Pendiente (implementar después de terminar features actuales)  
**Complejidad:** Alta — requiere onboarding DIAN por conjunto + integración API

---

##### Proveedor elegido: MATIAS API (Casa de Software)

| Plan | Precio | Facturas/mes | Multi-NIT |
|------|--------|-------------|-----------|
| Emprendedor | ~$180K COP/mes | 150 | No |
| **Casa de Software** | **~$920K COP/año** | ilimitadas | **Sí (client_company_id)** |
| Empresarial | ~$4.5M COP/año | ilimitadas | Sí |

**Por qué MATIAS API:**
- Soporte multi-NIT nativo (clave para SaaS con N conjuntos en el mismo plan)
- Python SDK disponible
- Certificado digital gestionado por MATIAS (no por nosotros)
- CUFE + PDF + XML + envío DIAN automático
- Contingencia T3/T4: hasta 5 días hábiles si DIAN cae

**Alternativas descartadas:**
- Siigo API: $200K+/mes por empresa, no multi-NIT en plan base
- Alegra API: similar precio, orientado a PYME individual
- Facturación directa DIAN: certificado propio ~$2.5M/año por NIT, sin SDK

---

##### Flujo de cobro en portería (portero escanea QR de salida)

```
1. Portero escanea QR vehicular de salida
   → Sistema ya tiene: cédula del visitante, placa, hora entrada

2. Sistema calcula tarifa (horas × valor_hora del conjunto)

3. Portero ve pantalla de cobro:
   ┌─────────────────────────────────────────┐
   │  Placa: ABC123  |  Tiempo: 2h 35min     │
   │  Total: $8.500 COP                      │
   │                                         │
   │  ¿Usar cédula 10234567 para factura?    │
   │  [Sí, usar esta cédula] [Ingresar otra] │
   └─────────────────────────────────────────┘

4. Si "Sí": usar cédula del QR → autocomplete nombre/email desde DIAN (API RUE)
   Si "Ingresar otra": campo manual de cédula/NIT

5. Selección medio de pago:
   [💳 QR Digital (Brebis)]  [💵 Efectivo]
   
   → La mayoría de conjuntos usarán Brebis QR
   → Brebis genera QR con valor exacto para Nequi/Bancolombia/Daviplata

6. ⚠️ REGLA CRÍTICA: la barrera sube INMEDIATAMENTE al confirmar pago
   → La factura se genera en background (celery task o threading)
   → NUNCA bloquear la barrera esperando respuesta DIAN

7. Background task:
   → POST a MATIAS API con datos del pago
   → DIAN emite CUFE + XML
   → Enviar factura PDF al email del visitante (si tiene)
   → Guardar en DB: cufe, xml_path, estado_dian
```

---

##### Snippet Python — Escenario A (consumidor final, sin RUT)

```python
import requests

def emitir_factura_parqueadero(conjunto, pago_data):
    """
    conjunto: instancia de ConjuntoResidencial (debe tener nit, api_key MATIAS)
    pago_data: dict con cedula, nombre, email, valor, minutos
    """
    payload = {
        "client_company_id": conjunto.matias_company_id,  # multi-NIT
        "document_type": "01",                             # factura de venta
        "customer": {
            "identification_type": "13",                   # cédula
            "identification": pago_data.get("cedula", "222222222222"),  # consumidor final si no hay
            "name": pago_data.get("nombre", "Consumidor Final"),
            "email": pago_data.get("email", ""),
        },
        "items": [{
            "description": f"Parqueadero {pago_data['minutos']} min",
            "quantity": 1,
            "unit_price": pago_data["valor"],
            "tax_rate": 0,                                 # parqueadero: IVA 0% en Colombia
        }],
        "payment_method": "10" if pago_data["medio"] == "efectivo" else "42",
    }
    
    resp = requests.post(
        "https://api.matiasapi.com/v1/invoices",
        json=payload,
        headers={"Authorization": f"Bearer {conjunto.matias_api_key}"},
        timeout=15
    )
    return resp.json()  # contiene cufe, pdf_url, xml_url
```

##### Snippet Python — Escenario B (empresa/persona con NIT registrado)

```python
# Mismo payload pero con NIT de empresa:
"customer": {
    "identification_type": "31",    # NIT
    "identification": "9001234567",  # NIT sin dígito verificación
    "dv": "8",
    "name": "Empresa S.A.S",
    "email": "contabilidad@empresa.com",
}
```

---

##### Modelo DB requerido (futuro)

```python
class PagoParqueadero(models.Model):
    conjunto = ForeignKey(ConjuntoResidencial, on_delete=CASCADE)
    visitante_vehicular = ForeignKey(VisitanteVehicular, on_delete=SET_NULL, null=True)
    cedula_factura = CharField(max_length=20)    # puede ser "222222222222" (consumidor final)
    nombre_factura = CharField(max_length=100)
    email_factura = EmailField(blank=True)
    valor = DecimalField(max_digits=10, decimal_places=2)
    minutos = PositiveIntegerField()
    medio_pago = CharField(choices=[('efectivo','Efectivo'),('qr_brebis','QR Brebis'),
                                     ('nequi','Nequi'),('bancolombia','Bancolombia')])
    # Factura DIAN
    cufe = CharField(max_length=200, blank=True)
    estado_dian = CharField(choices=[('pendiente','Pendiente'),('emitida','Emitida'),
                                      ('contingencia','Contingencia'),('error','Error')],
                             default='pendiente')
    xml_dian = TextField(blank=True)
    pdf_url = URLField(blank=True)
    factura_emitida_en = DateTimeField(null=True, blank=True)
    created_at = DateTimeField(auto_now_add=True)
```

---

##### Campos nuevos en ConjuntoResidencial (futuro)

```python
matias_company_id = CharField(max_length=50, blank=True, help_text='ID empresa en MATIAS API')
matias_api_key = CharField(max_length=200, blank=True, help_text='API key de MATIAS para este conjunto')
valor_hora_parqueadero_carro = DecimalField(max_digits=8, decimal_places=2, default=3000)
valor_hora_parqueadero_moto = DecimalField(max_digits=8, decimal_places=2, default=1500)
facturacion_electronica = BooleanField(default=False, help_text='Activar facturación electrónica DIAN')
```

---

##### 6 Riesgos documentados

| # | Riesgo | Mitigación |
|---|--------|-----------|
| 1 | DIAN caída | Contingencia T3/T4: guardar en `estado_dian='contingencia'`, reintentar con celery beat |
| 2 | IVA incorrecto | Parqueadero residencial: IVA 0%. Parqueadero comercial: IVA 19%. Validar con cada conjunto |
| 3 | Onboarding DIAN lento | Resolución de numeración + cert digital: 2–6 semanas. Avisar al admin al activar |
| 4 | Certificado digital vence | Vence cada 1–3 años. MATIAS lo gestiona en plan Casa de Software |
| 5 | Vendor lock-in MATIAS | Guardar siempre CUFE + XML propio. Migración posible con XML DIAN estándar |
| 6 | Privacidad cédulas | Encriptar cedula_factura con Fernet (ya existe en settings). Nunca logs de cédula |

---

##### Onboarding requerido por conjunto (antes de activar FE)

1. RUT del conjunto (ya deberían tenerlo)
2. Verificar IVA responsable (régimen común o simplificado)
3. Solicitar resolución de numeración ante DIAN (tramite en línea, 1–3 semanas)
4. MATIAS gestiona certificado digital firma electrónica (incluido en plan)
5. Registrar `matias_company_id` y `matias_api_key` en el panel SaaS del conjunto
6. Activar `facturacion_electronica = True` → se habilita el flujo en portería

---

##### Integración con Brebis (QR de cobro)

- Brebis es el agregador de pagos más usado en conjuntos colombianos (soporte Nequi + Bancolombia + Daviplata)
- API genera QR con valor fijo → portero muestra en pantalla o imprime
- Webhook de confirmación → actualizar `estado_pago` antes de subir barrera
- **Si Brebis no confirma en 30s → fallback a efectivo sin bloquear barrera**

---

##### Orden de implementación sugerido (sesión futura dedicada)

```
1. Agregar campos a ConjuntoResidencial (migration)
2. Crear modelo PagoParqueadero (migration)
3. Vista portería: pantalla de cobro (POST, no render completo)
4. Integración Brebis QR (webhook)
5. Background task emitir_factura_parqueadero (threading simple o celery)
6. Panel admin: historial pagos parqueadero + reenviar factura
7. Panel SaaS: activar facturación electrónica por conjunto
```

---

## Notas técnicas importantes

### Módulo Novedades

**Modelos** (`kislevsmart/models.py`):
```python
class Novedad(models.Model):
    conjunto = ForeignKey(ConjuntoResidencial, related_name='novedades')
    autor = ForeignKey(AUTH_USER_MODEL, related_name='novedades')
    titulo = CharField(max_length=200)
    imagen = ImageField(upload_to='novedades/imagenes/', null=True, blank=True)
    contenido = TextField()
    activa = BooleanField(default=True)  # soft delete
    created_at = DateTimeField(auto_now_add=True)

class ArchivoNovedad(models.Model):
    novedad = ForeignKey(Novedad, related_name='archivos')
    archivo = FileField(upload_to='novedades/archivos/')
    nombre_original = CharField(max_length=255)
    extension = CharField(max_length=20)  # 'pdf', 'excel', 'txt', 'otro'

class ComentarioNovedad(models.Model):
    novedad = ForeignKey(Novedad, related_name='comentarios')
    usuario = ForeignKey(AUTH_USER_MODEL)
    texto = TextField()
    created_at = DateTimeField(auto_now_add=True)

class LikeNovedad(models.Model):
    novedad = ForeignKey(Novedad, related_name='likes')
    usuario = ForeignKey(AUTH_USER_MODEL, related_name='likes_novedad')
    created_at = DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = [['novedad', 'usuario']]
```

**URLs** (`kislevsmart/urls.py`):
```
/novedades/                     → lista_novedades
/novedades/<pk>/                → detalle_novedad
/novedades/<pk>/comentar/       → agregar_comentario
/novedades/crear/               → crear_novedad
/novedades/<pk>/eliminar/       → eliminar_novedad
/novedades/<pk>/like/           → toggle_like (POST JSON)
/novedades/metricas/            → metricas_novedades
```

**toggle_like** retorna `{'liked': bool, 'total': int}`.

**Linkify JS** — función en detalle.html y comentarios convierte `https://...` a `<a>` clickeable.

---

### Módulo Auth — Cambiar/Recuperar Contraseña

**Cambiar contraseña (logueado):**
- View: `CustomPasswordChangeView` en `accounts/views.py`
- Usa `LoginRequiredMixin` + `update_session_auth_hash` para no cerrar sesión
- URL: `accounts:cambiar_password`
- Link en: `kislevsmart/templates/dashboard.html` sidebar

**Recuperar contraseña (sin email, por cédula):**
- View: `RecuperarPasswordView` en `accounts/views.py`
- Flujo 2 pasos: paso 1 verifica cédula (guarda user_id en sesión), paso 2 establece nueva contraseña
- URL: `accounts:recuperar_password`
- No requiere email — ideal para porteros que no tienen correo configurado

---

### Modelos financieros
- `Cuota`: cuotas de administración por conjunto. Campos: nombre, monto (COP), periodicidad, fecha_vencimiento.
- `Pago`: pago de un propietario a una cuota. unique_together=(cuota, propietario).
- Vistas admin: `finanzas_admin`, `crear_cuota`, `registrar_pago`
- Vista propietario: `estado_cuenta`

### AuditLog
- Helper `log_audit(request, accion, detalle)` en `kislevsmart/utils.py`
- Acciones: visitante_creado, qr_validado, qr_invalido, reserva_creada, reserva_fallida, login, logout

### Visitante FK a Conjunto
- `Visitante.conjunto` y `VisitanteVehicular.conjunto` → ForeignKey a ConjuntoResidencial
- DB column sigue siendo `usuario_id` (sin migración de datos, solo cambio de constraint)
- Filtrar siempre por `conjunto_id=request.user.conjunto_id`

### Rate limiting
- `RATELIMIT_ENABLED = not DEBUG` en settings.py
- `SILENCED_SYSTEM_CHECKS` activo en DEBUG para suprimir error de LocMemCache
- En producción funciona con Redis (REDIS_URL)

---

## Guía de migración a nuevo PC

> Código en GitHub: https://github.com/yagamidsa/Kislev.git  
> Stack actual: Python 3.13 + Django 5.1 + PostgreSQL 18

### Paso 1 — Instalar Python 3.13

1. Descargar desde: https://www.python.org/downloads/
2. Marcar **"Add Python to PATH"** durante la instalación
3. Verificar: `python --version` → `Python 3.13.x`

### Paso 2 — Instalar WeasyPrint (requiere GTK)

1. Descargar GTK3 runtime desde:  
   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
2. Instalar el `.exe` más reciente con todas las opciones por defecto
3. Reiniciar el PC después de instalar GTK

### Paso 3 — Instalar PostgreSQL

- Descargar PostgreSQL desde https://www.postgresql.org/download/windows/
- Durante la instalación anotar la contraseña del superusuario
- Puerto por defecto: 5432 (si ya hay otra versión puede quedar en 5433)

### Paso 4 — Crear base de datos

En pgAdmin o psql como superusuario:
```sql
CREATE DATABASE kislev;
CREATE USER kislev_user WITH PASSWORD 'kislev123';
GRANT ALL PRIVILEGES ON DATABASE kislev TO kislev_user;

-- Conectarse a la DB kislev y ejecutar:
GRANT ALL ON SCHEMA public TO kislev_user;
ALTER DATABASE kislev OWNER TO kislev_user;
ALTER USER kislev_user CREATEDB;
```

> **OJO:** Si hay múltiples versiones de PostgreSQL, verificar el puerto correcto y usar ese en DATABASE_URL.

### Paso 5 — Clonar el proyecto

```bash
git clone https://github.com/yagamidsa/Kislev.git
cd Kislev
```

### Paso 6 — Crear entorno virtual e instalar dependencias

```bash
python -m venv entornoV
entornoV\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

> Si hay errores de SSL: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt`

### Paso 7 — Crear archivo .env

```env
DJANGO_SECRET_KEY=genera-uno-con-el-comando-de-abajo
DEBUG=True
FERNET_KEY=genera-uno-con-el-comando-de-abajo
DATABASE_URL=postgres://kislev_user:kislev123@localhost:5432/kislev

# AWS SES — dejar vacío en local si no se envían emails reales
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SES_REGION=us-east-1
DEFAULT_FROM_EMAIL=noreply@kislev.net.co
```

> Ajustar puerto en DATABASE_URL según la instalación (5432 o 5433).

**Generar SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**Generar FERNET_KEY:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Paso 8 — Aplicar migraciones

```bash
python manage.py migrate
python manage.py runserver
```

Abrir http://127.0.0.1:8000 — debe cargar el login.

### Paso 9 — Poblar datos de prueba

Usar el script seed o el shell de Django para crear:
- 2 conjuntos: Oliva Madrid, Puerto Hayuelos 1
- 10 usuarios por conjunto (propietario + portero + admin)
- 6 salas por conjunto (Gym, Piscina, Sala de Juegos, Salón Eventos 1, Salón Eventos 2, BBQ)
- Parqueaderos: Oliva Madrid 30 carros + 10 motos / Puerto Hayuelos 50 carros + 10 motos

Las cédulas y contraseñas de usuarios de prueba están en `credenciales.txt` (no commitear — está en .gitignore).

### Paso 10 — Verificar tests

```bash
python -m pytest tests/ -v
```

Debe dar **20/20 pasando**.

### Paso 11 — Instalar Claude Code

```bash
npm install -g @anthropic/claude-code
```

Si no tienes Node.js: https://nodejs.org (versión LTS). Luego en la carpeta del proyecto: `claude`

---

### Checklist rápido nuevo PC

- [ ] Python 3.13 instalado y en PATH
- [ ] GTK3 runtime instalado (para WeasyPrint)
- [ ] PostgreSQL instalado y corriendo
- [ ] Base de datos `kislev` + usuario `kislev_user` creados con todos los GRANTs
- [ ] Repositorio clonado
- [ ] `entornoV` creado y `requirements.txt` instalado
- [ ] `.env` creado con SECRET_KEY, FERNET_KEY y DATABASE_URL correcto
- [ ] `python manage.py migrate` sin errores
- [ ] `python -m pytest tests/` → 20/20
- [ ] `python manage.py runserver` → abre en el browser

---

## Orden de ejecución recomendado — próximas sesiones

```
SESIÓN PRÓXIMA — Features restantes
  → F4 : Notificaciones push PWA (discutir opt-in por apartamento)
  → F6 : API REST DRF
  → F10: Predicción morosidad Claude API

SESIÓN T1 — Unificar modelos Visitante (sesión dedicada, alto riesgo)
  1. Nuevo modelo unificado con campo tipo
  2. Migración de datos (RunPython)
  3. Actualizar views y templates
```

---

## Flujo de trabajo con Claude Code

### Comando de inicio rápido
```bash
# Desde la raíz del proyecto
claude --dangerously-skip-permissions
```

### Patrón para tareas grandes (orquestador + sub-agentes)

```bash
# Sub-agente 1: modelos
claude -p "$(cat .claude/prompts/agente-modelos.txt) TAREA: ..."

# Sub-agente 2: vistas (después de que 1 termine)
claude -p "$(cat .claude/prompts/agente-vistas.txt) TAREA: ..."

# Sub-agente 3: frontend
claude -p "$(cat .claude/prompts/agente-frontend.txt) TAREA: ..."
```

---

## CLAUDE.md — pegar en la raíz del proyecto

```markdown
# Kislev — Contexto para Claude Code

## Proyecto
Sistema de gestión residencial Django para conjuntos en Colombia.
Deploy en Railway. Email via AWS SES (boto3, NO smtp).
Stack: Django 5.1 + Python 3.13 + PostgreSQL 18.

## Comandos útiles
- `python manage.py runserver`
- `python manage.py makemigrations && python manage.py migrate`

## REGLA #1 — RESPONSIVE OBLIGATORIO
Los usuarios usan principalmente celular (porteros, propietarios).
TODA vista nueva DEBE tener @media(max-width:600px) con:
- topbar: flex-wrap:wrap, padding reducido, font-size menor
- container: padding:14px 10px
- tablas: overflow-x:auto + min-width:500px
- formularios: width:100%, columnas apiladas
- cards: sin hover transform, padding reducido

## Convenciones
- Views: siempre @login_required + @role_required([...])
- APIs JSON: retornar {'status': 'ok'|'error', 'message': str}
- Inputs: sanitizar con sanitize_text() de kislevsmart/utils.py
- Email: EmailMultiAlternatives con fail_silently=False. Backend: Resend vía anymail en prod (RESEND_API_KEY), console en dev. Railway bloquea SMTP — NUNCA usar SMTP
- Fechas: siempre timezone-aware (America/Bogota)
- Moneda: COP, formatear con f"${valor:,.0f}"
- QR: siempre en memoria (BytesIO), nunca guardar en disco
- Cache: usar django.core.cache (apunta a Redis en Railway)
- AuditLog: llamar log_audit(request, accion, detalle) en acciones críticas

## NO hacer
- No guardar passwords en sesión → usar signing.dumps()
- No usar SMTP → Railway bloquea puertos 465 y 587. Usar Resend vía django-anymail (HTTP)
- No modificar migrations manualmente
- No hardcodear nombres de conjuntos en código nuevo
- No usar print() → usar logger.debug/info/error
- No guardar archivos en disco → usar BytesIO en memoria
- No hardcodear SECRET_KEY, FERNET_KEY ni credenciales
- No usar LocMemCache en producción → usar Redis
- No crear vistas sin @media(max-width:600px)

## Bugs conocidos pendientes
- T1: Visitante + VisitanteVehicular duplicados — pendiente unificar

## Reglas de scroll iOS (crítico)
- Siempre usar `height:100dvh` en `.scroll-root`, nunca solo `height:100%`
- Agregar `height:-webkit-fill-available` como fallback en html y .scroll-root
- Agregar `overscroll-behavior-y:contain` para evitar que iOS confunda límites
- Sin esto: scroll se pega al fondo o arriba en iPhone/Safari

## Email templates
- Estructura 100% tablas (no divs) para compatibilidad Outlook/Gmail
- Dark mode: `@media (prefers-color-scheme: dark)` + `[data-ogsc]` para Outlook
- Header con gradiente oscuro fijo — no se invierte en dark mode
- Botón CTA: fallback VML para Outlook Windows
- Nunca escribir "KislevSmart" — solo "Kislev"
```
