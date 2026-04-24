from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_add_cuota_almacenamiento'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersistentLoginToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='persistent_tokens',
                    to='accounts.usuario',
                )),
            ],
            options={
                'verbose_name': 'Token de login persistente',
                'db_table': 'persistent_login_tokens',
            },
        ),
    ]
