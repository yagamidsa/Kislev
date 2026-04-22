"""
Management command: prunar_novedades
Desactiva y elimina novedades con más de N días de antigüedad,
borrando también sus archivos e imágenes del storage (R2 o local).

Uso:
    python manage.py prunar_novedades            # elimina > 60 días
    python manage.py prunar_novedades --dias 30  # retención personalizada
    python manage.py prunar_novedades --dry-run  # solo muestra, no borra

Cron Railway (diario a las 3:30 AM):
    30 3 * * * python manage.py prunar_novedades
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Elimina novedades antiguas y sus archivos del storage'

    def add_arguments(self, parser):
        parser.add_argument('--dias',    type=int, default=60,
                            help='Días de retención (default 60)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra qué se borraría sin ejecutar nada')

    def handle(self, *args, **options):
        dias    = options['dias']
        dry_run = options['dry_run']
        corte   = timezone.now() - timedelta(days=dias)

        from kislevsmart.models import Novedad, ArchivoNovedad

        novedades = Novedad.objects.filter(created_at__lt=corte)
        total_nov = novedades.count()

        if total_nov == 0:
            self.stdout.write(self.style.SUCCESS(
                f'Sin novedades anteriores a {dias} días. Nada que eliminar.'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] Se eliminarían {total_nov} novedades (corte: {corte:%Y-%m-%d}).'))
            for n in novedades[:10]:
                self.stdout.write(f'  • [{n.conjunto}] {n.titulo[:60]} ({n.created_at:%Y-%m-%d})')
            if total_nov > 10:
                self.stdout.write(f'  … y {total_nov - 10} más.')
            return

        bytes_liberados = 0
        archivos_borrados = 0
        errores = 0

        for novedad in novedades:
            # ── Borrar imagen de portada ──────────────────────────────────
            if novedad.imagen:
                try:
                    bytes_liberados += novedad.imagen.size
                    novedad.imagen.delete(save=False)
                    archivos_borrados += 1
                except Exception as e:
                    logger.warning('[prunar_novedades] imagen %s: %s', novedad.pk, e)
                    errores += 1

            # ── Borrar archivos adjuntos ──────────────────────────────────
            for arch in ArchivoNovedad.objects.filter(novedad=novedad):
                try:
                    bytes_liberados += arch.archivo.size
                    arch.archivo.delete(save=False)
                    archivos_borrados += 1
                except Exception as e:
                    logger.warning('[prunar_novedades] archivo %s: %s', arch.pk, e)
                    errores += 1
                arch.delete()

            novedad.delete()

        mb = bytes_liberados / 1024 / 1024
        msg = (
            f'Novedades purgadas: {total_nov} | '
            f'Archivos eliminados: {archivos_borrados} | '
            f'Espacio liberado: {mb:.1f} MB'
            + (f' | Errores: {errores}' if errores else '')
        )
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info('[prunar_novedades] %s', msg)
