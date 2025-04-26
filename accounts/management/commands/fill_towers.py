from django.core.management.base import BaseCommand
from accounts.models import ConjuntoResidencial, Torre, Usuario

class Command(BaseCommand):
    help = 'Llena la tabla de torres con datos de ejemplo'

    def handle(self, *args, **kwargs):
        # Obtener todos los conjuntos residenciales
        conjuntos = ConjuntoResidencial.objects.all()

        if not conjuntos.exists():
            self.stdout.write(self.style.ERROR('No hay conjuntos residenciales. Por favor, crea al menos uno.'))
            return

        # Opciones para el usuario
        self.stdout.write(self.style.SUCCESS('Conjuntos residenciales disponibles:'))
        for i, conjunto in enumerate(conjuntos):
            self.stdout.write(f"{i+1}. {conjunto.nombre}")
        
        try:
            index = int(input("Seleccione el número del conjunto (o Enter para usar el primero): ") or "1") - 1
            conjunto = conjuntos[index]
        except (IndexError, ValueError):
            self.stdout.write(self.style.WARNING('Selección inválida. Usando el primer conjunto.'))
            conjunto = conjuntos[0]
        
        self.stdout.write(self.style.SUCCESS(f'Creando torres para: {conjunto.nombre}'))

        # Pedir detalles de torres y pisos
        try:
            num_torres = int(input("Ingrese el número de torres (por defecto 4): ") or "4")
            num_pisos = int(input("Ingrese el número de pisos por torre (por defecto 12): ") or "12")
            num_aptos = int(input("Ingrese el número de apartamentos por piso (por defecto 4): ") or "4")
            
            # Confirmar
            self.stdout.write(f"Se crearán {num_torres} torres con {num_pisos} pisos y {num_aptos} apartamentos por piso.")
            confirm = input("¿Continuar? (s/n): ").lower() or "s"
            
            if confirm != "s":
                self.stdout.write(self.style.ERROR('Operación cancelada.'))
                return
            
            # Crear torres
            torres_created = []
            for i in range(1, num_torres + 1):
                torre_nombre = f"Torre {i}"
                torre, created = Torre.objects.update_or_create(
                    conjunto=conjunto,
                    nombre=torre_nombre,
                    defaults={
                        'numero_pisos': num_pisos,
                        'aptos_por_piso': num_aptos,
                        'activo': True
                    }
                )
                
                status = 'creada' if created else 'actualizada'
                self.stdout.write(self.style.SUCCESS(f'Torre {torre_nombre} {status}'))
                torres_created.append(torre)

            # Crear también interiores/sectores
            create_interiors = input("¿Desea crear también interiores/sectores? (s/n): ").lower() or "s"
            if create_interiors == "s":
                num_interiores = int(input("Número de interiores/sectores (por defecto 2): ") or "2")
                pisos_interior = int(input("Pisos por interior (por defecto 3): ") or "3")
                aptos_piso_interior = int(input("Apartamentos por piso en interior (por defecto 6): ") or "6")
                
                for i in range(1, num_interiores + 1):
                    interior_nombre = f"Interior {i}"
                    interior, created = Torre.objects.update_or_create(
                        conjunto=conjunto,
                        nombre=interior_nombre,
                        defaults={
                            'numero_pisos': pisos_interior,
                            'aptos_por_piso': aptos_piso_interior,
                            'activo': True
                        }
                    )
                    
                    status = 'creado' if created else 'actualizado'
                    self.stdout.write(self.style.SUCCESS(f'Interior {interior_nombre} {status}'))
                    torres_created.append(interior)
            
            # Crear algunos propietarios de ejemplo
            crear_propietarios = input("¿Desea crear propietarios de ejemplo? (s/n): ").lower() or "n"
            if crear_propietarios == "s":
                num_propietarios = int(input("Número de propietarios a crear (por defecto 10): ") or "10")
                
                for i in range(1, num_propietarios + 1):
                    # Seleccionar torre aleatoria
                    import random
                    torre = random.choice(torres_created)
                    
                    # Generar apartamento aleatorio
                    piso = random.randint(1, torre.numero_pisos)
                    apto_num = random.randint(1, torre.aptos_por_piso)
                    apartamento = f"{piso}{apto_num:02d}"
                    
                    # Verificar si ya existe un usuario en ese apartamento
                    if Usuario.objects.filter(conjunto=conjunto, torre=torre, apartamento=apartamento).exists():
                        continue
                    
                    # Crear propietario
                    nombre = f"Propietario{i} {torre.nombre}-{apartamento}"
                    cedula = f"10{i:06d}"
                    email = f"prop{i}_{torre.nombre.replace(' ', '')}{apartamento}@example.com"
                    
                    try:
                        Usuario.objects.create(
                            cedula=cedula,
                            nombre=nombre,
                            email=email,
                            conjunto=conjunto,
                            user_type='propietario',
                            torre=torre,
                            apartamento=apartamento,
                            is_active=True
                        )
                        self.stdout.write(self.style.SUCCESS(f'Propietario creado: {nombre} ({torre.nombre}-{apartamento})'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error al crear propietario: {str(e)}'))
                
            self.stdout.write(self.style.SUCCESS('Proceso completado exitosamente.'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            return