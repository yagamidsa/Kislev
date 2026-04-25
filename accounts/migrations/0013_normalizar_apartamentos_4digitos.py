"""
Normaliza el campo `apartamento` de todos los usuarios a exactamente 4 dígitos
con ceros a la izquierda cuando el valor es puramente numérico y tiene menos de 4.

Ejemplos:
  "101"  → "0101"
  "4"    → "0004"
  "1205" → "1205"  (ya tiene 4)
  "Apto 3" → sin cambio (no es puramente numérico)
  ""     → sin cambio
"""
from django.db import migrations


def normalizar(apps, schema_editor):
    Usuario = apps.get_model('accounts', 'Usuario')
    to_update = []
    for u in Usuario.objects.exclude(apartamento='').exclude(apartamento__isnull=True):
        raw = u.apartamento.strip()
        if raw.isdigit() and len(raw) < 4:
            u.apartamento = raw.zfill(4)
            to_update.append(u)
    if to_update:
        Usuario.objects.bulk_update(to_update, ['apartamento'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_persistent_login_token'),
    ]

    operations = [
        migrations.RunPython(normalizar, migrations.RunPython.noop),
    ]
