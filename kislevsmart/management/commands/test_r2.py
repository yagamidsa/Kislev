"""
Diagnóstico rápido de R2: verifica config, sube archivo de prueba y genera URL.
Uso: python manage.py test_r2
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Diagnóstico de la conexión y configuración de Cloudflare R2'

    def handle(self, *args, **options):
        self.stdout.write('\n=== CONFIG R2 ===')
        self.stdout.write(f'DEFAULT_FILE_STORAGE : {settings.DEFAULT_FILE_STORAGE}')
        self.stdout.write(f'MEDIA_URL            : {settings.MEDIA_URL}')
        self.stdout.write(f'AWS_S3_ENDPOINT_URL  : {getattr(settings, "AWS_S3_ENDPOINT_URL", "NO SET")}')
        self.stdout.write(f'AWS_STORAGE_BUCKET   : {getattr(settings, "AWS_STORAGE_BUCKET_NAME", "NO SET")}')
        self.stdout.write(f'AWS_S3_CUSTOM_DOMAIN : {getattr(settings, "AWS_S3_CUSTOM_DOMAIN", "NO SET")}')
        self.stdout.write(f'AWS_QUERYSTRING_AUTH : {getattr(settings, "AWS_QUERYSTRING_AUTH", "NO SET")}')

        if 'S3Boto3' not in settings.DEFAULT_FILE_STORAGE:
            self.stdout.write(self.style.ERROR('\n⚠️  R2 NO activo — usando almacenamiento local'))
            self.stdout.write('Variables requeridas: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_ACCOUNT_ID')
            return

        self.stdout.write('\n=== TEST UPLOAD ===')
        try:
            import boto3
            from botocore.exceptions import ClientError

            s3 = boto3.client(
                's3',
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name='auto',
            )

            # Subir archivo de prueba
            key = '_test_kislev_r2_check.txt'
            s3.put_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key, Body=b'ok')
            self.stdout.write(self.style.SUCCESS('✓ Upload OK'))

            # URL pública esperada
            domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
            if domain:
                url = f'https://{domain}/{key}'
            else:
                url = f'{settings.AWS_S3_ENDPOINT_URL}/{settings.AWS_STORAGE_BUCKET_NAME}/{key}'
            self.stdout.write(f'URL pública: {url}')

            # Verificar acceso HTTP
            import urllib.request
            try:
                req = urllib.request.urlopen(url, timeout=5)
                self.stdout.write(self.style.SUCCESS(f'✓ Acceso público OK (HTTP {req.status})'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Acceso público FALLA: {e}'))
                self.stdout.write('→ El bucket necesita "Public Development URL" habilitado en Cloudflare R2')

            # Limpiar
            s3.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ ERROR: {e}'))
