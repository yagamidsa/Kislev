"""
Management command: prunar_auditlog
Elimina entradas de AuditLog con más de N días de antigüedad (por defecto 90).

Uso:
    python manage.py prunar_auditlog            # elimina entradas > 90 días
    python manage.py prunar_auditlog --dias 30  # retención de 30 días

Ejecutar periódicamente con un cron de Railway o equivalente:
    0 3 * * * python manage.py prunar_auditlog
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Elimina registros de AuditLog con más de N días de antigüedad'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=90,
            help='Días de retención (por defecto 90)',
        )

    def handle(self, *args, **options):
        dias = options['dias']
        corte = timezone.now() - timedelta(days=dias)

        from kislevsmart.models import AuditLog
        qs = AuditLog.objects.filter(fecha__lt=corte)
        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(f'AuditLog limpio — ningún registro anterior a {dias} días.'))
            return

        qs.delete()
        msg = f'AuditLog: {total} registros eliminados (anteriores a {dias} días / corte: {corte:%Y-%m-%d}).'
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info('[prunar_auditlog] %s', msg)
