from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_tipo_distribucion'),
        ('kislevsmart', '0018_visitante_guardado'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigGlobal',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('limite_emails_mes', models.PositiveIntegerField(default=1000, help_text='Límite mensual de emails (AWS SES)')),
                ('limite_whatsapp_mes', models.PositiveIntegerField(default=500, help_text='Límite mensual de WhatsApp (Twilio)')),
            ],
            options={
                'verbose_name': 'Configuración Global',
                'verbose_name_plural': 'Configuración Global',
                'db_table': 'config_global',
            },
        ),
        migrations.CreateModel(
            name='LogEnvio',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('email', 'Email'), ('whatsapp', 'WhatsApp')], max_length=10)),
                ('fecha', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('detalle', models.CharField(blank=True, max_length=200)),
                ('conjunto', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='log_envios',
                    to='accounts.conjuntoresidencial',
                )),
            ],
            options={
                'verbose_name': 'Log de Envío',
                'verbose_name_plural': 'Logs de Envíos',
                'db_table': 'log_envio',
                'ordering': ['-fecha'],
            },
        ),
    ]
