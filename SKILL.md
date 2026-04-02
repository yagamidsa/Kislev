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
                         Cuota, Pago, AuditLog  ← NUEVOS
  views.py            ← ~1900 líneas (pendiente dividir en módulos)
  urls.py
  utils.py            ← role_required (reexporta de accounts), log_audit
accounts/             ← auth, ConjuntoResidencial, Torre, Usuario
  models.py
  views.py
  backends.py
  utils.py            ← role_required (fuente canónica)
```

**Stack:** Django 3.2 + PostgreSQL · Railway (deploy) · Redis (cache/sesiones) · AWS SES (email boto3) · Whitenoise · django-ratelimit

**Dominio:** kislev.net.co · **Moneda:** COP (pesos colombianos) · **TZ:** America/Bogota

**⚠️ Python 3.7** — bloqueador para subir a Django 5.1 (requiere Python 3.10+)

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
- DB: PostgreSQL en Railway
- Modelos existentes: ConjuntoResidencial, Torre, Usuario(AbstractBaseUser),
  Visitante, VisitanteVehicular, Sala, Reserva,
  ParqueaderoCarro, ParqueaderoMoto, Cuota, Pago, AuditLog

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
- views.py tiene ~1900 líneas — NO lo reescribas completo, solo añade/edita funciones
- Auth: login_required + verificación de user_type ('administrador','propietario','porteria')
- Email: usar send_ses_email(to, subject, body) que ya existe en utils
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
Eres un agente de frontend para Kislev (Django templates + Tailwind/Bootstrap).
Contexto:
- Templates en kislevsmart/templates/ y accounts/templates/
- Estáticos en kislevsmart/static/
- UI en español, mercado colombiano
- Existen: dashboard, portería QR, salas, notificaciones, parking,
           historial visitantes (propietario), finanzas (admin + propietario)

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Extiende siempre de base.html o la plantilla padre existente
- No uses {% load static %} si ya está en el padre
- Formularios con csrf_token siempre
- Diseño mobile-first (porteros usan celular)
- Mensajes de éxito/error con el sistema de messages de Django
```

---

### 🔴 AGENTE: Infraestructura / DevOps
```
Eres un agente de infraestructura para Kislev en Railway.
Contexto:
- Deploy: Railway (bloquea puertos SMTP estándar)
- Email: AWS SES API via boto3 (NO usar SMTP)
- Variables de entorno en Railway: DATABASE_URL, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY, AWS_SES_REGION, DJANGO_SECRET_KEY, REDIS_URL, FERNET_KEY
- Estáticos: Whitenoise + CompressedManifestStaticFilesStorage
- Rate limiting: RATELIMIT_ENABLED=not DEBUG (requiere Redis en prod)

TAREA: [DESCRIBE AQUÍ]

Reglas:
- Nunca hardcodees credenciales
- Usa os.environ.get() con default seguro
- Si cambias settings.py, verifica que no rompa DEBUG=False
- Para Redis: django-redis con CACHE_BACKEND url
```

---

## BACKLOG — Estado actualizado al 2026-04-02

### ✅ COMPLETADO esta sesión

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

---

### 🔴 PENDIENTE — Crítico / Alta prioridad

#### [T2] Django 3.2 EOL → Django 5.1
**Bloqueador:** Python 3.7 en uso. Django 5.1 requiere Python 3.10+.
**Orden correcto:**
1. Actualizar Python 3.7 → 3.12
2. Limpiar requirements.txt (quitar sendgrid, waitress que ya no se usan)
3. Actualizar Django + dependencias
4. Resolver breaking changes (USE_L10N, conn_health_checks ya hecho)

#### [T1] Unificar Visitante + VisitanteVehicular
**Complejidad:** Alta — requiere migración de datos.
Unificar en un solo modelo con campo `tipo` ('peatonal', 'vehicular') y campos vehiculares opcionales. Dashboard actualmente no incluye visitantes vehiculares en estadísticas.

---

### 🚀 BLOQUE 6 — Features pendientes

| # | Feature | Estado | Complejidad |
|---|---------|--------|-------------|
| F1 | Módulo financiero: Cuota + Pago + EstadoCuenta | ✅ Hecho | — |
| F2 | Historial de visitantes por apartamento | ✅ Hecho | — |
| F3 | Solicitar SES producción AWS | ⏳ Trámite externo | Baja (gestión) |
| F4 | Notificaciones push PWA | ⏳ Pendiente | Media |
| F5 | Reporte PDF mensual (WeasyPrint) | ✅ Hecho | — |
| F6 | API REST con DRF para app móvil | ⏳ Pendiente | Alta |
| F7 | AuditLog — registro de acciones críticas | ✅ Hecho | — |
| F8 | Dashboard financiero (conectar a Cuota/Pago) | ✅ Hecho | — |
| F9 | Tests con pytest-django para flujos críticos | ✅ Hecho — 20/20 | — |
| F10 | Predicción morosidad con Claude API | ⏳ Pendiente | Alta |

---

## Notas técnicas importantes

### Modelos financieros (nuevos)
- `Cuota`: cuotas de administración por conjunto. Campos: nombre, monto (COP), periodicidad, fecha_vencimiento.
- `Pago`: pago de un propietario a una cuota. unique_together=(cuota, propietario) — un pago por cuota por propietario.
- Vistas admin: `finanzas_admin`, `crear_cuota`, `registrar_pago`
- Vista propietario: `estado_cuenta`

### AuditLog
- Helper `log_audit(request, accion, detalle)` en `kislevsmart/utils.py`
- Acciones disponibles: visitante_creado, qr_validado, qr_invalido, reserva_creada, reserva_fallida, login, logout
- Llamar en todas las acciones críticas nuevas

### Visitante FK a Conjunto
- `Visitante.conjunto` y `VisitanteVehicular.conjunto` → ForeignKey a ConjuntoResidencial
- DB column sigue siendo `usuario_id` (sin migración de datos, solo cambio de constraint)
- Filtrar siempre por `conjunto_id=request.user.conjunto_id`

### Rate limiting
- `RATELIMIT_ENABLED = not DEBUG` en settings.py
- `SILENCED_SYSTEM_CHECKS` activo en DEBUG para suprimir error de LocMemCache
- En producción funciona con Redis (REDIS_URL)

### .env local
- Archivo `.env` creado para desarrollo local (no commitear)
- `.env.example` en el repo documenta todas las variables necesarias

---

## Orden de ejecución recomendado — próximas sesiones

```
SESIÓN PRÓXIMA — Features restantes
  → F4 : Notificaciones push PWA (discutir opt-in por apartamento)
  → F6 : API REST DRF
  → F10: Predicción morosidad Claude API

SESIÓN T2 — Actualización Python + Django (sesión dedicada, alto riesgo)
  1. pip install python 3.12 (fuera del proyecto)
  2. Recrear virtualenv con Python 3.12
  3. Limpiar requirements.txt (quitar sendgrid, waitress)
  4. pip install "django>=5.1,<5.2"
  5. Resolver breaking changes

SESIÓN T1 — Unificar modelos Visitante (sesión dedicada)
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

### Guardar prompts de agentes en `.claude/prompts/`
```
.claude/
  prompts/
    agente-modelos.txt      ← copia el bloque 🔵 aquí
    agente-vistas.txt       ← copia el bloque 🟢 aquí
    agente-frontend.txt     ← copia el bloque 🟡 aquí
    agente-infra.txt        ← copia el bloque 🔴 aquí
  CLAUDE.md                 ← contexto global (ver abajo)
```

---

## CLAUDE.md — pegar en la raíz del proyecto

```markdown
# Kislev — Contexto para Claude Code

## Proyecto
Sistema de gestión residencial Django para conjuntos en Colombia.
Deploy en Railway. Email via AWS SES (boto3, NO smtp).

## Comandos útiles
- `python manage.py runserver`
- `python manage.py makemigrations && python manage.py migrate`
- `python manage.py fill_towers` — poblar datos de prueba

## Convenciones
- Views: siempre @login_required + @role_required([...])
- APIs JSON: retornar {'status': 'ok'|'error', 'message': str}
- Inputs: sanitizar con sanitize_text() de kislevsmart/utils.py
- Email: usar función send_ses_email() centralizada, nunca EmailMessage directo
- Fechas: siempre timezone-aware (America/Bogota)
- Moneda: COP, formatear con f"${valor:,.0f}"
- QR: siempre en memoria (BytesIO), nunca guardar en disco
- Cache: usar django.core.cache (apunta a Redis en Railway)
- AuditLog: llamar log_audit(request, accion, detalle) en acciones críticas

## NO hacer
- No guardar passwords en sesión → usar signing.dumps()
- No usar SMTP → Railway lo bloquea, usar AWS SES API
- No modificar migrations manualmente
- No hardcodear nombres de conjuntos en código nuevo
- No usar print() → usar logger.debug/info/error
- No guardar archivos en disco → usar BytesIO en memoria
- No hardcodear SECRET_KEY, FERNET_KEY ni credenciales
- No usar LocMemCache en producción → usar Redis

## Modelos financieros
- Cuota: cuotas por conjunto (monto en COP)
- Pago: pago de propietario a cuota (unique_together: cuota+propietario)
- EstadoCuenta: calculado en vista estado_cuenta (no es modelo)

## Bugs conocidos pendientes
- T1: Visitante + VisitanteVehicular duplicados — pendiente unificar
- T2: Django 3.2 EOL — pendiente (bloqueado por Python 3.7)
```
