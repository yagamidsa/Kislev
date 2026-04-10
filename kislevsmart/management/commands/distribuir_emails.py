from django.core.management.base import BaseCommand
from accounts.models import Usuario


class Command(BaseCommand):
    help = 'Distribuye dos emails de prueba entre todos los usuarios de forma alternada'

    def handle(self, *args, **options):
        emails = ['david.alipio@kislev.net.co', 'yagamidsa@hotmail.com']
        usuarios = Usuario.objects.all().order_by('id')
        total = usuarios.count()

        for i, usuario in enumerate(usuarios):
            email = emails[i % 2]
            usuario.email = email
            usuario.save(update_fields=['email'])
            self.stdout.write(f"  {usuario.username} → {email}")

        self.stdout.write(self.style.SUCCESS(f"\n✓ {total} usuarios actualizados."))
