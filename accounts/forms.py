from django import forms
from .models import ConjuntoResidencial
from django.core.validators import MinLengthValidator

class LoginForm(forms.Form):
    cedula = forms.CharField(
        label='Cédula',
        min_length=5,  # Longitud mínima típica de una cédula
        max_length=20,  # Longitud máxima razonable
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese su cédula',
            'autocomplete': 'off',  # Prevenir autocompletado para mayor seguridad
            'pattern': '[0-9]*',  # Solo permitir números
            'inputmode': 'numeric'  # Teclado numérico en móviles
        })
    )
    
    conjunto = forms.ModelChoiceField(
        queryset=ConjuntoResidencial.objects.filter(estado=True),
        label='Conjunto Residencial',
        empty_label="Seleccione un conjunto",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'aria-label': 'Seleccione su conjunto residencial'  # Mejora accesibilidad
        })
    )
    
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese su contraseña',
            'autocomplete': 'current-password',  # Mejor manejo de autocompletado de contraseñas
            'aria-label': 'Contraseña'  # Mejora accesibilidad
        })
    )

    def clean_cedula(self):
        """Validación específica para el campo cédula"""
        cedula = self.cleaned_data.get('cedula')
        if not cedula.isdigit():
            raise forms.ValidationError('La cédula debe contener solo números.')
        return cedula

    def clean(self):
        cleaned_data = super().clean()
        cedula = cleaned_data.get('cedula')
        conjunto = cleaned_data.get('conjunto')
        
        if cedula and conjunto:
            from .models import Usuario
            try:
                usuario = Usuario.objects.get(cedula=cedula, conjunto=conjunto)
                cleaned_data['usuario'] = usuario
            except Usuario.DoesNotExist:
                raise forms.ValidationError(
                    'No existe un usuario con esta cédula en el conjunto seleccionado.'
                )
            except Exception as e:
                # Log the error if you have logging configured
                raise forms.ValidationError(
                    'Error al validar las credenciales. Por favor, intente nuevamente.'
                )
        
        return cleaned_data

    class Meta:
        fields = ['conjunto', 'cedula', 'password']