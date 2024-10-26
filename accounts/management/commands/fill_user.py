from django.core.management.base import BaseCommand
from accounts.models import Usuario

class Command(BaseCommand):
    help = 'Llena la tabla de usuarios con datos ficticios'

    def handle(self, *args, **kwargs):
        usuarios = [
            {
                'email': 'yagamidsa@hotmail.com',
                'password': '123456',
                'phone_number': '3118026851',
            },
            {
                'email': 'test@gmail.com',
                'password': '123456',
                'phone_number': '3118026851',
            },
            # Agrega más usuarios según sea necesario
        ]

        for user_data in usuarios:
            user = Usuario(
                email=user_data['email'],
                phone_number=user_data['phone_number'],
            )
            user.set_password(user_data['password'])  # Asegúrate de usar set_password
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Usuario creado: {user.email}'))
