from django.db import models
from accounts.models import User


class ManagementCase(models.Model):
    DIFFICULTY_CHOICES = [
        ('basico', 'Básico'), ('intermedio', 'Intermedio'), ('avanzado', 'Avanzado'),
    ]
    CATEGORY_CHOICES = [
        ('conflicto', 'Manejo de Conflictos'), ('comunicacion', 'Comunicación Efectiva'),
        ('delegacion', 'Delegación'), ('motivacion', 'Motivación de Equipos'),
        ('decision', 'Toma de Decisiones'), ('cambio', 'Gestión del Cambio'),
    ]

    title = models.CharField('Título', max_length=200)
    description = models.TextField('Descripción del caso')
    category = models.CharField('Categoría', max_length=30, choices=CATEGORY_CHOICES)
    difficulty = models.CharField('Dificultad', max_length=20, choices=DIFFICULTY_CHOICES, default='basico')
    is_active = models.BooleanField(default=True)
    key_competencies = models.TextField('Competencias clave', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_difficulty_display()}] {self.title}"

    class Meta:
        verbose_name = 'Caso Gerencial'
        verbose_name_plural = 'Casos Gerenciales'


# ── Diagnóstico inicial ────────────────────────────────────────────────────────

class DiagnosisSession(models.Model):
    STATUS_CHOICES = [
        ('en_progreso', 'En Progreso'),
        ('completado', 'Completado — esperando revisión coach'),
        ('aprobado', 'Aprobado por Coach'),
        ('rechazado', 'Rechazado por Coach'),
        ('nivel_asignado', 'Nivel Asignado'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='diagnosis_session')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_progreso')
    current_question = models.IntegerField(default=1)   # 1 al 5
    ia_level_suggestion = models.CharField(max_length=20, blank=True)
    ia_summary = models.TextField('Resumen IA del diagnóstico', blank=True)
    # Validación del coach sobre las 5 preguntas
    coach = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_diagnoses', limit_choices_to={'role': 'coach'}
    )
    coach_approved = models.BooleanField(null=True, blank=True)   # True=aprobado, False=rechazado
    coach_verdict = models.TextField('Dictamen del Coach sobre el diagnóstico', blank=True)
    coach_reviewed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Diagnóstico de {self.user.get_full_name()}"

    class Meta:
        verbose_name = 'Sesión de Diagnóstico'
        verbose_name_plural = 'Sesiones de Diagnóstico'


class DiagnosisMessage(models.Model):
    ROLE_CHOICES = [('user', 'Usuario'), ('assistant', 'IA')]

    session = models.ForeignKey(DiagnosisSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    question_number = models.IntegerField(null=True, blank=True)   # a qué pregunta corresponde
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


# ── Casos gerenciales + chatbox ────────────────────────────────────────────────

class CaseSession(models.Model):
    STATUS_CHOICES = [
        ('en_progreso', 'En Progreso'),
        ('completado', 'Completado — pendiente revisión coach'),
        ('en_revision', 'En Revisión por Coach'),
        ('evaluado', 'Evaluado'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='case_sessions')
    case = models.ForeignKey(ManagementCase, on_delete=models.CASCADE, related_name='sessions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_progreso')
    score = models.IntegerField('Puntuación IA', null=True, blank=True)
    ia_feedback = models.TextField('Retroalimentación IA', blank=True)
    # Dictamen del Coach
    coach = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_sessions', limit_choices_to={'role': 'coach'}
    )
    coach_verdict = models.TextField('Dictamen del Coach', blank=True)
    coach_approved = models.BooleanField(null=True, blank=True)   # True=aprobado, False=rechazado
    coach_reviewed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.case.title}"

    class Meta:
        verbose_name = 'Sesión de Caso'
        verbose_name_plural = 'Sesiones de Casos'


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'Usuario'), ('assistant', 'Asistente IA'), ('system', 'Sistema'),
    ]
    MESSAGE_TYPE_CHOICES = [
        ('normal', 'Normal'),
        ('quick_reply', 'Respuesta Rápida'),   # botones de acuerdo/desacuerdo
        ('error_ia', 'Error de IA'),
        ('system_info', 'Info del Sistema'),
    ]

    session = models.ForeignKey(CaseSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='normal')
    # Para quick replies: guardamos la opción elegida y la razón dada
    quick_reply_option = models.CharField(max_length=50, blank=True)   # 'agree'|'disagree'|'incomplete'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Mensaje de Chat'
        verbose_name_plural = 'Mensajes de Chat'


# ── Registro de errores de IA ──────────────────────────────────────────────────

class IAErrorLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ia_errors')
    session = models.ForeignKey(CaseSession, on_delete=models.SET_NULL, null=True, blank=True)
    error_type = models.CharField(max_length=100)
    error_detail = models.TextField(blank=True)
    notified_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Error IA — {self.user.username} — {self.created_at:%d/%m/%Y %H:%M}"

    class Meta:
        verbose_name = 'Error de IA'
        verbose_name_plural = 'Errores de IA'
        ordering = ['-created_at']
