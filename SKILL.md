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
