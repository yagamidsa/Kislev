from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_add_horario_atencion'),
    ]

    operations = [
        migrations.AddField(
            model_name='conjuntoresidencial',
            name='cuota_almacenamiento_mb',
            field=models.PositiveIntegerField(
                default=2048,
                help_text='Espacio máximo en MB que puede usar este conjunto para archivos e imágenes (default 2 GB).',
            ),
        ),
    ]
