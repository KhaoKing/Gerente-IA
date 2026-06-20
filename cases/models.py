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
        ('completado', 'Esperando validación del MAE'),
        ('aprobado', 'Aprobado por MAE'),
        ('rechazado', 'Rechazado por MAE'),
        ('nivel_asignado', 'Nivel Asignado'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='diagnosis_session')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_progreso')
    current_question = models.IntegerField(default=1)   # 1 al 5
    ia_level_suggestion = models.CharField(max_length=20, blank=True)
    ia_summary = models.TextField('Resumen IA del diagnóstico', blank=True)
    # Validación del MAE sobre las 5 preguntas
    mae = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_diagnoses', limit_choices_to={'role': 'mae'}
    )
    mae_approved = models.BooleanField(null=True, blank=True)   # True=aprobado, False=rechazado
    mae_verdict = models.TextField('Dictamen del MAE sobre el diagnóstico', blank=True)
    mae_reviewed_at = models.DateTimeField(null=True, blank=True)
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

    def __str__(self):
        return f"Pregunta {self.question_number or '?'} — {self.get_role_display()} ({self.created_at:%d/%m %H:%M})"

    class Meta:
        ordering = ['created_at']


# ── Casos gerenciales + chatbox ────────────────────────────────────────────────

class CaseSession(models.Model):
    STATUS_CHOICES = [
        ('en_progreso', 'En Progreso'),
        ('completado', 'Completado'),
        ('en_revision', 'En Revisión por MAE'),
        ('evaluado', 'Evaluado'),
        ('abandoned', 'Abandonada'),
    ]
    PHASE_CHOICES = [
        ('ambiguity', 'Fase 1: Ambigüedad'),
        ('pressure', 'Fase 2: Presión'),
        ('dilemma', 'Fase 3: Dilema'),
        ('completed', 'Fases Completadas'),
    ]
    ABANDONMENT_REASON_CHOICES = [
        ('electrical_failure', 'Falla eléctrica'),
        ('internet_loss', 'Pérdida de internet'),
        ('user_frustration', 'Frustración del usuario'),
        ('other', 'Otro'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='case_sessions')
    case = models.ForeignKey(ManagementCase, on_delete=models.CASCADE, related_name='sessions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_progreso')
    current_phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='ambiguity')
    # Variables acumuladoras del algoritmo NC_hs
    n_interactions = models.IntegerField('Variable n: total de ciclos', default=0)
    acumulado_ac = models.IntegerField('Variable Ac: Acoplamientos Exitosos', default=0)
    acumulado_sm = models.IntegerField('Variable Sm: Sincronía Metódica', default=0)
    acumulado_ts = models.IntegerField('Variable Ts: Trauma Sistémico', default=0)
    nchs_score = models.DecimalField('Índice NC_hs', max_digits=4, decimal_places=3, default=0.000)
    # Dictamen del MAE
    mae = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_sessions', limit_choices_to={'role': 'mae'}
    )
    teacher = models.ForeignKey(
        'TeacherProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supervised_sessions'
    )
    mae_verdict = models.TextField('Dictamen del MAE', blank=True)
    mae_approved = models.BooleanField(null=True, blank=True)
    mae_reviewed_at = models.DateTimeField(null=True, blank=True)
    ia_feedback = models.TextField('Retroalimentación IA', blank=True)
    # Abandono por fallas de entorno
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    abandonment_reason = models.CharField(max_length=50, null=True, blank=True, choices=ABANDONMENT_REASON_CHOICES)
    abandonment_justification = models.TextField(blank=True)
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
        ('quick_reply', 'Respuesta Rápida'),
        ('error_ia', 'Error de IA'),
        ('system_info', 'Info del Sistema'),
    ]
    ENTROPY_NODE_CHOICES = [
        ('ambiguity', 'Ambigüedad'),
        ('time_pressure', 'Presión Temporal'),
        ('ethical_dilemma', 'Dilema Ético'),
    ]
    CLASSIFICATION_CHOICES = [
        ('Ac', 'Acoplamiento Exitoso'),
        ('Sm', 'Sincronía Metódica'),
        ('Ts', 'Trauma Sistémico'),
    ]

    session = models.ForeignKey(CaseSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='normal')
    quick_reply_option = models.CharField(max_length=50, blank=True)
    # Clasificación del LLM (evaluación de segundo orden)
    classification_variable = models.CharField(max_length=2, null=True, blank=True, choices=CLASSIFICATION_CHOICES)
    ai_justification = models.TextField(blank=True)
    # Nodo de entropía forzada
    entropy_node = models.CharField(max_length=20, choices=ENTROPY_NODE_CHOICES, default='ambiguity')
    # Telemetría fina (milisegundos)
    latency_reading_ms = models.IntegerField('Tiempo de lectura (ms)', null=True, blank=True)
    latency_execution_ms = models.IntegerField('Tiempo de ejecución (ms)', null=True, blank=True)
    backspace_count = models.IntegerField('Conteo de backspaces', null=True, blank=True)
    # Métricas legacy (segundos) — mantenidas para compatibilidad
    response_time_seconds = models.FloatField('Tiempo de respuesta (seg)', null=True, blank=True)
    total_pause_seconds = models.FloatField('Tiempo en pausa (seg)', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_role_display()} — {self.get_message_type_display()} ({self.created_at:%d/%m %H:%M})"

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Mensaje de Chat'
        verbose_name_plural = 'Mensajes de Chat'


# ── Perfil del Docente / Observador de Segundo Orden ────────────────────────────

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    academic_degree = models.CharField('Grado académico', max_length=100)
    institution_origin = models.CharField('Institución de origen', max_length=100)
    research_line = models.CharField('Línea de investigación', max_length=150)
    is_active_tutor = models.BooleanField('Tutor activo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Docente: {self.user.get_full_name()} — {self.academic_degree}"

    class Meta:
        verbose_name = 'Perfil de Docente'
        verbose_name_plural = 'Perfiles de Docentes'


# ── Pre-evaluación (línea base del ego antes de la sesión) ──────────────────────

class PreEvaluation(models.Model):
    session = models.OneToOneField(CaseSession, on_delete=models.CASCADE, related_name='pre_evaluation')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pre_evaluations')
    perceived_control_score = models.IntegerField('Control percibido (1-5)')
    ia_trust_baseline = models.IntegerField('Confianza en IA (1-5)')
    initial_ego_statement = models.TextField('Declaración del ego inicial')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pre-eval de {self.user.get_full_name()} — Sesión {self.session_id}"

    class Meta:
        verbose_name = 'Pre-evaluación'
        verbose_name_plural = 'Pre-evaluaciones'


# ── Post-autopsia cognitiva (reflexión tras la crisis) ──────────────────────────

class PostAutopsy(models.Model):
    session = models.OneToOneField(CaseSession, on_delete=models.CASCADE, related_name='post_autopsy')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_autopsies')
    shock_reflection = models.TextField('Reflexión del choque')
    negotiation_strategy = models.TextField('Estrategia de negociación')
    law_sovereignty = models.TextField('Ley 1: Protocolo de última palabra')
    law_identity = models.TextField('Ley 4: Elemento inalterable')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Post-autopsia de {self.user.get_full_name()} — Sesión {self.session_id}"

    class Meta:
        verbose_name = 'Post-autopsia'
        verbose_name_plural = 'Post-autopsias'


# ── Configuración de API de IA ─────────────────────────────────────────────────

class AIConfiguration(models.Model):
    PROVIDER_CHOICES = [
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
        ('groq', 'Groq'),
        ('mistral', 'Mistral AI'),
        ('together', 'Together AI'),
        ('openai_compatible', 'Otro (OpenAI Compatible)'),
    ]

    PROVIDER_ENDPOINTS = {
        'gemini': 'https://generativelanguage.googleapis.com/v1beta/models/',
        'openai': 'https://api.openai.com/v1/chat/completions',
        'deepseek': 'https://api.deepseek.com/v1/chat/completions',
        'groq': 'https://api.groq.com/openai/v1/chat/completions',
        'mistral': 'https://api.mistral.ai/v1/chat/completions',
        'together': 'https://api.together.xyz/v1/chat/completions',
    }

    name = models.CharField('Nombre', max_length=100, default='Default')
    provider = models.CharField('Proveedor', max_length=20, choices=PROVIDER_CHOICES, default='gemini')
    api_url = models.URLField('URL del endpoint', help_text='URL completa del endpoint de la API')
    api_key = models.CharField('API Key', max_length=500)
    model_name = models.CharField('Nombre del modelo', max_length=100, blank=True,
                                  help_text='Solo para OpenAI/compatibles. Ej: gpt-4o, deepseek-chat')
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()})"

    class Meta:
        verbose_name = 'Configuración de IA'
        verbose_name_plural = 'Configuraciones de IA'

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()


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
