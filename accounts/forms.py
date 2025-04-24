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

    class Meta:
        fields = ['cedula', 'password']


class SelectConjuntoForm(forms.Form):
    conjunto = forms.ModelChoiceField(
        queryset=None,  # Se establecerá dinámicamente
        label='Conjunto Residencial',
        empty_label=None,  # No queremos opción vacía
        widget=forms.Select(attrs={
            'class': 'form-control',
            'aria-label': 'Seleccione su conjunto residencial'
        })
    )
    
    def __init__(self, conjuntos, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['conjunto'].queryset = conjuntos