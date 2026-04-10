"""
Django settings for kislevsmart project.
"""

import environ
import os
from pathlib import Path
import dj_database_url

# Inicialización de environ
env = environ.Env(
    DEBUG=(bool, False)
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
_env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(_env_file):
    environ.Env.read_env(_env_file)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or os.environ.get('SECRET_KEY')
FERNET_KEY = os.environ.get('FERNET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

# Configuración de hosts
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [
        '.railway.app',
        'kislev.net.co',
        'www.kislev.net.co',
        'localhost',
        '127.0.0.1',
    ]

# Configuraciones de Seguridad según el entorno
if DEBUG:
    # Configuraciones para desarrollo
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_BROWSER_XSS_FILTER = False
    SECURE_CONTENT_TYPE_NOSNIFF = False
    SECURE_PROXY_SSL_HEADER = None
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
else:
    # Configuraciones para producción
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = not DEBUG
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Configuraciones de Cookie
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Configuración de sesión
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600  # 1 hora
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'kislevsmart',
    'django_ratelimit',
    'whitenoise.runserver_nostatic',
]

# Configuración de middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'kislevsmart.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'kislevsmart', 'templates'),
            os.path.join(BASE_DIR, 'accounts', 'templates'),
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'kislevsmart.wsgi.application'

# Database configuration
if os.getenv('DATABASE_URL', None):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL'),
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'login',
            'USER': 'yagami',
            'PASSWORD': 'Ipsos2012*',
            'HOST': 'localhost',
            'PORT': '5432',
            'ATOMIC_REQUESTS': True,
            'OPTIONS': {
                'isolation_level': 1,  # READ COMMITTED isolation level
                'connect_timeout': 10,
            },
        }
    }

# Auth settings
AUTH_USER_MODEL = 'accounts.Usuario'

AUTHENTICATION_BACKENDS = (
    'accounts.backends.CedulaConjuntoBackend',
    'django.contrib.auth.backends.ModelBackend',
)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Configuración de formato para fechas
DATE_INPUT_FORMATS = [
    '%d/%m/%Y',
    '%d-%m-%Y',
    '%Y-%m-%d',
]

TIME_INPUT_FORMATS = [
    '%H:%M:%S',
    '%H:%M',
]

DATETIME_INPUT_FORMATS = [
    '%d/%m/%Y %H:%M:%S',
    '%d/%m/%Y %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
]

# Configuración para archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'kislevsmart', 'static'),
    os.path.join(BASE_DIR, 'accounts', 'static'),
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Configuración de archivos media
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# CONFIGURACIÓN DE EMAIL CON AMAZON SES
# ============================================

# AWS SES Configuration - Usando API (recomendado para mejor rendimiento)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_SES_REGION_NAME = os.environ.get('AWS_SES_REGION', 'us-east-1')
AWS_SES_REGION_ENDPOINT = f'email.{AWS_SES_REGION_NAME}.amazonaws.com'

# WhatsApp Cloud API (Meta)
META_WHATSAPP_TOKEN = os.environ.get('META_WHATSAPP_TOKEN', '')
META_WHATSAPP_PHONE_ID = os.environ.get('META_WHATSAPP_PHONE_ID', '')

# WhatsApp via Twilio
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')

# Configuración del backend de email
# Si hay credenciales de AWS configuradas, usar SES con API
# Si no, usar SMTP como fallback o console en desarrollo
if os.environ.get('AWS_SES_ACCESS_KEY_ID') and os.environ.get('AWS_SES_SECRET_ACCESS_KEY'):
    EMAIL_BACKEND = 'django_ses.SESBackend'
    AWS_SES_ACCESS_KEY_ID = os.environ.get('AWS_SES_ACCESS_KEY_ID')
    AWS_SES_SECRET_ACCESS_KEY = os.environ.get('AWS_SES_SECRET_ACCESS_KEY')
    AWS_SES_REGION_NAME = os.environ.get('AWS_SES_REGION_NAME', 'us-east-1')
    AWS_SES_REGION_ENDPOINT = f"email.{os.environ.get('AWS_SES_REGION_NAME', 'us-east-1')}.amazonaws.com"
else:
    if DEBUG:
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    else:
        EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Email por defecto para envíos
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'yagamidsa@hotmail.com')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Configuración adicional de email
EMAIL_TIMEOUT = 30
EMAIL_USE_LOCALTIME = False

# URL de login
LOGIN_URL = '/accounts/login/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Configuración de caché
if os.environ.get('REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.environ.get('REDIS_URL'),
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'TIMEOUT': 300,
        }
    }

# Configuración de logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING' if not DEBUG else 'INFO',
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'django_ses': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
    },
}

# Rate limiting: desactivado en desarrollo local (requiere Redis compartido)
RATELIMIT_ENABLED = not DEBUG
# Silenciar checks de ratelimit cuando no hay Redis (LocMemCache no es shared cache)
if DEBUG or not os.environ.get('REDIS_URL'):
    SILENCED_SYSTEM_CHECKS = ['django_ratelimit.E003', 'django_ratelimit.W001']

# Configuración de CSRF
CSRF_TRUSTED_ORIGINS = []
if not DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        'https://*.railway.app',
        'https://kislev.net.co',
        'https://www.kislev.net.co',
    ]