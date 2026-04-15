"""
Management command to create the SaaS super-owner account.
Run once on initial deployment:

    python manage.py create_saas_owner \
        --cedula 1234567890 \
        --nombre "David Admin" \
        --email admin@kislev.net.co \
        --password SuperSecret123
"""
from django.core.management.base import BaseCommand, CommandError
from accounts.models import Usuario, ConjuntoResidencial


class Command(BaseCommand):
    help = 'Crea o actualiza el usuario SaaS owner (accede a todos los conjuntos)'

    def add_arguments(self, parser):
        parser.add_argument('--cedula', required=True)
        parser.add_argument('--nombre', required=True)
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)

    def handle(self, *args, **options):
        cedula = options['cedula']
        nombre = options['nombre']
        email = options['email']
        password = options['password']

        # El saas_owner necesita un conjunto; usa el primero existente
        # (o crea uno dummy si no hay ninguno)
        conjunto = ConjuntoResidencial.objects.first()
        if not conjunto:
            conjunto = ConjuntoResidencial.objects.create(
                nombre='KislevSaaS',
                direccion='N/A',
                nit='000000000',
            )
            self.stdout.write(f'  Conjunto dummy creado: {conjunto.nombre}')

        # Busca por cedula + conjunto para no violar unique_together
        try:
            usuario = Usuario.objects.get(cedula=cedula, conjunto=conjunto)
            usuario.nombre = nombre
            usuario.email = email
            usuario.set_password(password)
            usuario.is_staff = True
            usuario.is_superuser = True
            usuario.is_saas_owner = True
            usuario.user_type = 'administrador'
            usuario.save()
            self.stdout.write(self.style.WARNING(f'SaaS owner actualizado: {usuario}'))
        except Usuario.DoesNotExist:
            usuario = Usuario.objects.create_user(
                cedula=cedula,
                nombre=nombre,
                email=email,
                password=password,
                conjunto=conjunto,
                is_staff=True,
                is_superuser=True,
                is_saas_owner=True,
                user_type='administrador',
            )
            self.stdout.write(self.style.SUCCESS(f'SaaS owner creado: {usuario}'))
