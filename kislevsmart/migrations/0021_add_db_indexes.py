"""
Fix #2 Escalabilidad — Índices de base de datos para consultas frecuentes.

Modelos afectados:
- Visitante: email_creador, fecha_generacion
- VisitanteVehicular: email_creador, fecha_generacion, (conjunto, ultima_lectura)
- AuditLog: fecha
- Novedad: (conjunto, activa, created_at)
- NovedadVista: (novedad, usuario) ya tiene unique_together; agregamos índice en usuario solo
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kislevsmart', '0020_alter_configglobal_id_alter_logenvio_id'),
    ]

    operations = [
        # ── Visitante ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='visitante',
            index=models.Index(fields=['email_creador'], name='vis_email_creador_idx'),
        ),
        migrations.AddIndex(
            model_name='visitante',
            index=models.Index(fields=['fecha_generacion'], name='vis_fecha_gen_idx'),
        ),

        # ── VisitanteVehicular ─────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='visitantevehicular',
            index=models.Index(fields=['email_creador'], name='visveh_email_creador_idx'),
        ),
        migrations.AddIndex(
            model_name='visitantevehicular',
            index=models.Index(fields=['fecha_generacion'], name='visveh_fecha_gen_idx'),
        ),
        migrations.AddIndex(
            model_name='visitantevehicular',
            index=models.Index(fields=['conjunto', 'ultima_lectura'], name='visveh_conj_ulect_idx'),
        ),

        # ── AuditLog ───────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['fecha'], name='audit_fecha_idx'),
        ),

        # ── Novedad ────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='novedad',
            index=models.Index(fields=['conjunto', 'activa', 'created_at'], name='novedad_conj_activa_idx'),
        ),

        # ── NovedadVista ───────────────────────────────────────────────────────
        # unique_together ya genera índice compuesto (novedad, usuario).
        # Añadimos índice inverso (usuario) para lookups por usuario.
        migrations.AddIndex(
            model_name='novedadvista',
            index=models.Index(fields=['usuario'], name='novedadvista_usuario_idx'),
        ),
    ]
