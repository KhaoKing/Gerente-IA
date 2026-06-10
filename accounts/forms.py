from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.hashers import make_password
from .models import User, ManagerProfile


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario',
        widget=forms.TextInput(attrs={'placeholder': 'Correo o usuario'})
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'})
    )


class ManagerProfileForm(forms.ModelForm):
    first_name = forms.CharField(label='Nombre(s)', max_length=50)
    last_name = forms.CharField(label='Apellido(s)', max_length=50)

    class Meta:
        model = ManagerProfile
        fields = ['position', 'company', 'industry', 'experience_years', 'team_size', 'main_challenge']
        labels = {
            'position': 'Cargo actual', 'company': 'Empresa',
            'industry': 'Industria', 'experience_years': 'Años de experiencia',
            'team_size': 'Tamaño de tu equipo', 'main_challenge': 'Principal reto como gerente',
        }
        widgets = {
            'main_challenge': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: Manejo de conflictos, delegación...'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

    def save(self, user, commit=True):
        profile = super().save(commit=False)
        profile.user = user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.profile_completed = True
        if commit:
            user.save()
            profile.save()
        return profile


class CreateUserForm(forms.Form):
    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('mae', 'MAE'),
    ]

    username = forms.CharField(label='Usuario', max_length=150)
    email = forms.EmailField(label='Correo electrónico', required=False)
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
        min_length=6,
    )
    role = forms.ChoiceField(label='Rol', choices=ROLE_CHOICES)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Este usuario ya existe.')
        return username

    def save(self):
        data = self.cleaned_data
        user = User.objects.create(
            username=data['username'],
            email=data.get('email', ''),
            password=make_password(data['password']),
            role=data['role'],
            profile_completed=False,
        )
        return user


class RegistrationForm(forms.Form):
    username = forms.CharField(label='Usuario', max_length=150)
    email = forms.EmailField(label='Correo electrónico')
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
        min_length=6,
    )
    first_name = forms.CharField(label='Nombre(s)', max_length=50)
    last_name = forms.CharField(label='Apellido(s)', max_length=50)
    position = forms.CharField(label='Cargo actual', max_length=100)
    company = forms.CharField(label='Empresa', max_length=100)
    industry = forms.ChoiceField(label='Industria', choices=ManagerProfile.INDUSTRY_CHOICES)
    experience_years = forms.ChoiceField(label='Años de experiencia', choices=ManagerProfile.EXPERIENCE_CHOICES)
    team_size = forms.ChoiceField(label='Tamaño de tu equipo', choices=ManagerProfile.TEAM_SIZE_CHOICES)
    main_challenge = forms.CharField(
        label='Principal reto como gerente',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: Manejo de conflictos, delegación...'}),
        required=False,
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Este usuario ya existe.')
        return username

    def save(self):
        data = self.cleaned_data
        user = User.objects.create(
            username=data['username'],
            email=data['email'],
            password=make_password(data['password']),
            first_name=data['first_name'],
            last_name=data['last_name'],
            role='gerente',
            profile_completed=True,
        )
        ManagerProfile.objects.create(
            user=user,
            position=data['position'],
            company=data['company'],
            industry=data['industry'],
            experience_years=data['experience_years'],
            team_size=data['team_size'],
            main_challenge=data.get('main_challenge', ''),
        )
        return user


class AdminMaeProfileForm(forms.Form):
    first_name = forms.CharField(label='Nombre(s)', max_length=50)
    last_name = forms.CharField(label='Apellido(s)', max_length=50)

    def save(self, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.profile_completed = True
        user.save()
        return user
