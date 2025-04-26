# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),  # Actualiza la dependencia a la migración previa
    ]

    operations = [
        migrations.CreateModel(
            name='Torre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Nombre de la torre o interior (ej: Torre 1, Interior A)', max_length=100)),
                ('numero_pisos', models.PositiveIntegerField(default=1, help_text='Número de pisos en esta torre')),
                ('aptos_por_piso', models.PositiveIntegerField(default=4, help_text='Número de apartamentos por piso')),
                ('activo', models.BooleanField(default=True)),
                ('conjunto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='torres', to='accounts.conjuntoresidencial')),
            ],
            options={
                'verbose_name': 'Torre/Interior',
                'verbose_name_plural': 'Torres/Interiores',
                'unique_together': {('conjunto', 'nombre')},
            },
        ),
        # Eliminamos la operación AddField para 'apartamento' ya que ya existe
        migrations.AddField(
            model_name='usuario',
            name='torre',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='residentes', to='accounts.torre'),
        ),
    ]