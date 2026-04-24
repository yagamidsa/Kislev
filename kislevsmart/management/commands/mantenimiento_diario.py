"""
Comando único que agrupa todas las tareas de mantenimiento diario:
  1. Limpiar sesiones Django expiradas (clearsessions)
  2. Purgar registros de auditoría con más de N días (prunar_auditlog)
  3. Purgar novedades con más de N días (prunar_novedades)
  4. Purgar tokens de login persistente expirados

Uso:
    python manage.py mantenimiento_diario
    python manage.py mantenimiento_diario --dry-run

Cron Railway (diario a las 3:00 AM):
    0 3 * * * python manage.py mantenimiento_diario
"""
import logging
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Mantenimiento diario: limpia sesiones, audit log y novedades antiguas'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra que se borraria sin ejecutar nada')
        parser.add_argument('--dias-audit', type=int, default=90,
                            help='Dias de retencion para audit log (default 90)')
        parser.add_argument('--dias-novedades', type=int, default=60,
                            help='Dias de retencion para novedades (default 60)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write('=== Mantenimiento diario Kislev ===')

        # 1. Sesiones expiradas
        self.stdout.write('\n[1/4] Limpiando sesiones expiradas...')
        if not dry_run:
            call_command('clearsessions', verbosity=0)
            self.stdout.write(self.style.SUCCESS('OK Sesiones limpiadas'))
        else:
            self.stdout.write('dry-run: se ejecutaria clearsessions')

        # 2. Audit log
        self.stdout.write(f'\n[2/4] Purgando audit log (>{options["dias_audit"]} dias)...')
        if dry_run:
            self.stdout.write(f'dry-run: se ejecutaria prunar_auditlog --dias {options["dias_audit"]}')
        else:
            call_command('prunar_auditlog', dias=options['dias_audit'])

        # 3. Novedades antiguas
        self.stdout.write(f'\n[3/4] Purgando novedades (>{options["dias_novedades"]} dias)...')
        if dry_run:
            self.stdout.write(f'dry-run: se ejecutaria prunar_novedades --dias {options["dias_novedades"]}')
        else:
            call_command('prunar_novedades', dias=options['dias_novedades'])

        # 4. Tokens de login persistente expirados
        self.stdout.write('\n[4/4] Purgando tokens de login expirados...')
        if dry_run:
            from accounts.models import PersistentLoginToken
            count = PersistentLoginToken.objects.filter(expires_at__lt=timezone.now()).count()
            self.stdout.write(f'dry-run: se eliminarian {count} tokens expirados')
        else:
            from accounts.models import PersistentLoginToken
            deleted, _ = PersistentLoginToken.objects.filter(expires_at__lt=timezone.now()).delete()
            self.stdout.write(self.style.SUCCESS(f'OK {deleted} tokens expirados eliminados'))

        self.stdout.write(self.style.SUCCESS('\nMantenimiento completado.'))
        logger.info('[mantenimiento_diario] completado — dry_run=%s', dry_run)
