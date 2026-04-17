"""
Replace the tipo_distribucion enum with two free-text fields:
  nombre_agrupacion — e.g. "Torre", "Bloque", "" (empty = no grouping)
  nombre_unidad     — e.g. "Apto", "Casa"

Data migration converts existing enum values to the new fields.
"""
from django.db import migrations, models

_MAPPING = {
    'torre_apto':    ('Torre',    'Apto'),
    'interior_apto': ('Interior', 'Apto'),
    'bloque_apto':   ('Bloque',   'Apto'),
    'manzana_casa':  ('Manzana',  'Casa'),
    'solo_apto':     ('',         'Apto'),
    'solo_casa':     ('',         'Casa'),
}


def populate_new_fields(apps, schema_editor):
    ConjuntoResidencial = apps.get_model('accounts', 'ConjuntoResidencial')
    for obj in ConjuntoResidencial.objects.all():
        tipo = getattr(obj, 'tipo_distribucion', 'torre_apto') or 'torre_apto'
        agrupacion, unidad = _MAPPING.get(tipo, ('Torre', 'Apto'))
        obj.nombre_agrupacion = agrupacion
        obj.nombre_unidad = unidad
        obj.save(update_fields=['nombre_agrupacion', 'nombre_unidad'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_tipo_distribucion'),
    ]

    operations = [
        # 1. Add new fields (nullable first so existing rows don't break)
        migrations.AddField(
            model_name='conjuntoresidencial',
            name='nombre_agrupacion',
            field=models.CharField(
                blank=True,
                default='Torre',
                help_text='Nombre del nivel de agrupación (ej: Torre, Bloque, Interior). Dejar vacío si no hay agrupación.',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='conjuntoresidencial',
            name='nombre_unidad',
            field=models.CharField(
                default='Apto',
                help_text='Nombre de la unidad mínima (ej: Apto, Casa, PH).',
                max_length=50,
            ),
        ),
        # 2. Populate from old enum
        migrations.RunPython(populate_new_fields, migrations.RunPython.noop),
        # 3. Remove old enum field
        migrations.RemoveField(
            model_name='conjuntoresidencial',
            name='tipo_distribucion',
        ),
    ]
