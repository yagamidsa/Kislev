from django import forms

class LoginForm(forms.Form):
    usuario = forms.IntegerField()  # Cambiar a IntegerField si es un número
    password = forms.CharField(widget=forms.PasswordInput)
