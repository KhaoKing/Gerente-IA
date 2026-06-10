from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('mae', 'MAE'),
        ('gerente', 'Gerente'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='gerente')
    profile_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_admin_role(self): return self.role == 'admin' or self.is_superuser
    @property
    def is_mae(self): return self.role == 'mae'
    @property
    def is_gerente(self): return self.role == 'gerente'


class ManagerProfile(models.Model):
    INDUSTRY_CHOICES = [
        ('tecnologia', 'Tecnología'), ('finanzas', 'Finanzas'),
        ('salud', 'Salud'), ('retail', 'Retail'),
        ('manufactura', 'Manufactura'), ('educacion', 'Educación'), ('otro', 'Otro'),
    ]
    EXPERIENCE_CHOICES = [
        ('0-2', 'Menos de 2 años'), ('2-5', '2 a 5 años'),
        ('5-10', '5 a 10 años'), ('10+', 'Más de 10 años'),
    ]
    TEAM_SIZE_CHOICES = [
        ('1-5', '1 a 5 personas'), ('6-15', '6 a 15 personas'),
        ('16-50', '16 a 50 personas'), ('50+', 'Más de 50 personas'),
    ]
    LEVEL_CHOICES = [
        ('sin_nivel', 'Sin nivel asignado'),
        ('basico', 'Básico'),
        ('intermedio', 'Intermedio'),
        ('avanzado', 'Avanzado'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='manager_profile')
    position = models.CharField('Cargo actual', max_length=100)
    company = models.CharField('Empresa', max_length=100)
    industry = models.CharField('Industria', max_length=50, choices=INDUSTRY_CHOICES)
    experience_years = models.CharField('Años de experiencia', max_length=10, choices=EXPERIENCE_CHOICES)
    team_size = models.CharField('Tamaño del equipo', max_length=10, choices=TEAM_SIZE_CHOICES)
    main_challenge = models.TextField('Principal reto', blank=True)
    # Nivel asignado tras diagnóstico
    level = models.CharField('Nivel', max_length=20, choices=LEVEL_CHOICES, default='sin_nivel')
    level_assigned_at = models.DateTimeField(null=True, blank=True)
    diagnosis_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.user.get_full_name()}"
