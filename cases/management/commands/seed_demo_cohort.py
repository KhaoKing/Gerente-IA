"""
Genera un lote de gerentes demo con diagnóstico aprobado y los casos disponibles
en la BD rotados entre ellos (cada caso se usa al menos una vez), recorriendo el
flujo real de la app (vistas reales vía Client) para que las métricas del
dashboard salgan consistentes con el resto del sistema.

Cada sesión de caso queda con su content_hash (sha256 del caso + transcripción
completa) al cerrarse, para poder detectar sesiones con contenido duplicado.

La IA se fuerza a modo fallback (sin llamadas reales a Gemini/OpenAI) para que
esto corra rápido, sin costo de API y sin depender de que haya una key
configurada — el fallback simulado del propio proyecto ya varía la
clasificación (Ac/Sm/Ts) y el texto por mensaje.

Uso:
    python manage.py seed_demo_cohort
    python manage.py seed_demo_cohort --count 5 --password Demo2026!
"""
import json
import random
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, ManagerProfile
from cases.models import ManagementCase, CaseSession, DiagnosisSession

FIRST_NAMES = [
    'Andrea', 'Miguel', 'Fernanda', 'Diego', 'Valentina', 'Ricardo', 'Camila',
    'Jorge', 'Paola', 'Alejandro', 'Daniela', 'Sebastián', 'Gabriela', 'Mauricio',
    'Lucía', 'Emilio', 'Renata', 'Rodrigo', 'Ximena', 'Iván',
]
LAST_NAMES = [
    'Rojas', 'Herrera', 'Castillo', 'Morales', 'Vega', 'Solís', 'Aguilar',
    'Campos', 'Núñez', 'Reyes', 'Delgado', 'Fuentes', 'Cordero', 'Salazar',
    'Mendoza', 'Vargas', 'Chacón', 'Araya', 'Jiménez', 'Quesada',
]
POSITIONS = [
    'Gerente de Operaciones', 'Gerente Comercial', 'Jefe de Proyecto',
    'Coordinador de Equipo', 'Gerente de RRHH', 'Supervisor de Planta', 'Líder de Producto',
]
COMPANIES = [
    'Grupo Andino S.A.', 'Tecnofin', 'Corporación Delta', 'Innovatex',
    'Distribuidora Central', 'Logística Norte', 'Servicios Integrales CR',
]
CHALLENGES = [
    'Manejar equipos con distintos niveles de experiencia sin perder cohesión.',
    'Tomar decisiones rápidas cuando la información es incompleta.',
    'Delegar sin sentir que pierdo el control de los resultados.',
    'Mantener la motivación del equipo en periodos de mucha presión.',
    'Comunicar cambios organizacionales sin generar resistencia excesiva.',
]

DIAGNOSIS_ANSWER_POOL = {
    1: [
        "Reuniría de inmediato al colaborador para entender el error y luego llamaría al cliente para ofrecer una disculpa y un plan concreto.",
        "Priorizaría contener el daño con el cliente primero, y después revisaría internamente qué falló.",
        "Delegaría la comunicación con el cliente a mi mejor negociador mientras yo reviso los hechos con el colaborador.",
        "Actuaría rápido: reconocería el error ante el cliente y propondría una solución provisional en los primeros quince minutos.",
    ],
    2: [
        "Hablaría con cada uno por separado antes de sentarlos juntos a buscar un acuerdo.",
        "Establecería reglas claras de convivencia y daría seguimiento semanal a la relación entre ambos.",
        "Los reuniría a los tres para exponer el impacto en el equipo y acordar compromisos concretos.",
        "Buscaría entender el origen del conflicto antes de imponer una solución.",
    ],
    3: [
        "Elegiría a la persona con más experiencia y le daría autoridad clara, no solo tareas.",
        "Delegaría por etapas, empezando con lo de menor riesgo, y superviso de cerca al inicio.",
        "Sería explícito sobre expectativas, plazos y el nivel de decisión que puede tomar por su cuenta.",
        "Buscaría a alguien que ya haya mostrado iniciativa antes, aunque no tenga toda la experiencia.",
    ],
    4: [
        "Sería honesto con el equipo sobre la situación y enfocaría la conversación en lo que sí podemos controlar.",
        "Organizaría una reunión breve para escuchar sus preocupaciones antes de hablar de soluciones.",
        "Reconocería el esfuerzo del equipo abiertamente y buscaría otras formas de motivación no monetarias.",
        "Hablaría individualmente con quienes veo más afectados antes de dirigirme a todo el equipo.",
    ],
    5: [
        "Empezaría analizando los datos de rendimiento actuales para identificar los cuellos de botella.",
        "Plantearía dos o tres iniciativas concretas con responsables y métricas claras, en vez de un plan genérico.",
        "Involucraría al equipo en el diagnóstico antes de proponer el plan, para que se sientan parte de la solución.",
        "Presentaría un plan con logros rápidos a treinta días y objetivos más ambiciosos a noventa días.",
    ],
}

PHASE_ANSWER_POOL = {
    'ambiguity': [
        "Primero reuniría a los involucrados por separado para entender qué pasó realmente antes de sacar conclusiones.",
        "Necesito más información antes de decidir: revisaría los datos disponibles y hablaría con el equipo directamente.",
        "Empezaría por escuchar a todas las partes de forma individual para no tomar partido de entrada.",
        "Analizaría el impacto real en el equipo y en los resultados antes de decidir cualquier acción.",
        "Buscaría entender la causa de fondo del problema antes de proponer una solución rápida.",
        "Hablaría primero con mi jefe para alinear expectativas y luego reuniría al equipo completo.",
    ],
    'pressure': [
        "Tomaría una decisión rápida con la información que tengo y comunicaría el plan de inmediato al equipo.",
        "Escalaría el tema a mi jefe mientras implemento una solución temporal para contener el impacto.",
        "Priorizaría lo urgente, delegaría tareas específicas y daría seguimiento cada dos horas.",
        "Convocaría una reunión de emergencia con los responsables clave para acordar una acción conjunta.",
        "Negociaría un plazo adicional mientras ejecuto la solución más viable en paralelo.",
        "Asumiría el riesgo de una decisión imperfecta ahora, y ajustaría el curso según los resultados.",
    ],
    'dilemma': [
        "No aceptaría saltar el proceso interno, aunque sea más lento: prefiero mantener la confianza del equipo.",
        "Buscaría una alternativa intermedia que no comprometa la ética ni sacrifique del todo la eficiencia.",
        "Sería transparente con el equipo sobre el riesgo, aunque la decisión sea incómoda.",
        "Tomaría la solución eficiente, pero documentaría bien la decisión para poder justificarla después.",
        "Consultaría con Recursos Humanos antes de proceder con algo que pueda afectar la moral del equipo.",
        "Preferiría asumir el costo reputacional a corto plazo antes que perder la confianza de mi equipo.",
    ],
}

QR_DISPLAY = {'agree': '✅ Estoy de acuerdo', 'disagree': '❌ No estoy de acuerdo', 'incomplete': '🤔 Creo que falta algo'}
QUICK_REPLY_REASONS = {
    'agree': [
        "Coincido totalmente porque ya he vivido una situación similar en mi equipo.",
        "Me parece el camino correcto dado el poco margen de tiempo que hay.",
        "Estoy de acuerdo, priorizar así reduce el riesgo para el cliente.",
    ],
    'disagree': [
        "No estoy de acuerdo, creo que actuar tan rápido puede generar más problemas después.",
        "Prefiero una alternativa distinta porque el equipo podría sentirse ignorado.",
        "Discrepo porque no se está considerando el impacto a largo plazo.",
    ],
    'incomplete': [
        "Creo que falta considerar cómo se siente el equipo con esta decisión.",
        "Falta un plan de seguimiento después de tomar la acción inmediata.",
        "No se menciona cómo comunicar esto al resto de la organización.",
    ],
}

DIAG_VERDICTS = [
    "Respuestas sólidas y bien fundamentadas. Nivel confirmado.",
    "Buen razonamiento general, con oportunidades de profundizar en el manejo de personas.",
    "Muestra criterio práctico, aunque podría estructurar mejor sus decisiones.",
    "Diagnóstico aprobado. Se recomienda reforzar comunicación asertiva en los próximos casos.",
]
CASE_VERDICTS = [
    "Buen manejo del caso, identificó los puntos clave en cada fase.",
    "Demostró criterio bajo presión, aunque puede mejorar en el manejo del dilema ético.",
    "Aprobado. Se recomienda reforzar la delegación con autoridad real.",
    "Buen desempeño general, cierre de caso satisfactorio.",
]


class Command(BaseCommand):
    help = (
        "Genera N gerentes demo (diagnóstico aprobado por el Docente Tutor + "
        "un caso cerrado con conversaciones variadas) para producir métricas de cierre."
    )

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5)
        parser.add_argument('--password', type=str, default='Demo2026!')

    def handle(self, *args, **options):
        count = options['count']
        password = options['password']

        mae = User.objects.filter(role='mae').first()
        if not mae:
            self.stderr.write(self.style.ERROR(
                "No hay ningún usuario Docente Tutor (role='mae'). Corre "
                "'python manage.py load_initial_data' primero."
            ))
            return

        cases = list(ManagementCase.objects.filter(is_active=True).order_by('id'))
        if not cases:
            self.stderr.write(self.style.ERROR(
                "No hay casos activos (ManagementCase). Corre "
                "'python manage.py load_initial_data' primero."
            ))
            return

        start_idx = User.objects.filter(username__startswith='gerente_demo').count() + 1

        # La IA se fuerza a modo fallback: sin llamadas reales a la API, rápido,
        # sin costo, y el propio fallback del proyecto ya varía texto y clasificación.
        with patch('cases.ai_engine._ai_available', return_value=False):
            users = []
            for i in range(count):
                idx = start_idx + i
                user = self._create_user(idx, password)
                self._create_manager_profile(user, idx)
                self._run_diagnosis(user, mae)
                users.append(user)
                self.stdout.write(
                    f"  ✓ Diagnóstico aprobado: {user.get_full_name()} ({user.username}) "
                    f"— nivel={user.manager_profile.level}"
                )

            self.stdout.write(f"\nRotando {len(cases)} casos entre {len(users)} gerentes...\n")
            for case_idx, case in enumerate(cases):
                user = users[case_idx % len(users)]
                overdue = (case_idx % 3 == 0)
                session = self._run_case_chat(user, mae, case, overdue)
                self.stdout.write(
                    f"  ✓ {user.get_full_name()} ({user.username}) — caso='{case.title}', "
                    f"NC_hs={session.nchs_score}, hash={session.content_hash[:12] if session.content_hash else '—'}..."
                )

        call_command('check_sla')

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {count} gerentes demo generados, {len(cases)} sesiones de caso rotadas "
            f"(usuarios: {users[0].username}..{users[-1].username}). "
            f"Password para todos: {password}"
        ))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _create_user(self, idx, password):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        username = f'gerente_demo{idx:02d}'
        return User.objects.create_user(
            username=username, password=password, role='gerente',
            email=f'{username}@demo.gerenteia.com',
            first_name=first, last_name=last,
        )

    def _create_manager_profile(self, user, idx):
        ManagerProfile.objects.create(
            user=user,
            position=random.choice(POSITIONS),
            company=random.choice(COMPANIES),
            industry=random.choice([c[0] for c in ManagerProfile.INDUSTRY_CHOICES]),
            experience_years=random.choice([c[0] for c in ManagerProfile.EXPERIENCE_CHOICES]),
            team_size=random.choice([c[0] for c in ManagerProfile.TEAM_SIZE_CHOICES]),
            main_challenge=random.choice(CHALLENGES),
        )

    def _telemetry(self):
        return {
            'response_time_seconds': random.randint(25, 190),
            'total_pause_seconds': random.randint(0, 35),
            'latency_reading_ms': random.randint(300, 4500),
            'latency_execution_ms': random.randint(1200, 16000),
            'backspace_count': random.randint(0, 14),
        }

    def _run_diagnosis(self, user, mae):
        client = Client()
        client.force_login(user)
        client.get(reverse('start_diagnosis'))
        for q in range(1, 6):
            answer = random.choice(DIAGNOSIS_ANSWER_POOL[q])
            client.post(
                reverse('diagnosis_send'),
                data=json.dumps({'message': answer}),
                content_type='application/json',
            )
        client.logout()

        d_session = DiagnosisSession.objects.get(user=user)
        mae_client = Client()
        mae_client.force_login(mae)
        mae_client.post(reverse('mae_diagnosis_review', args=[d_session.id]), data={
            'mae_verdict': random.choice(DIAG_VERDICTS),
            'mae_approved': 'true',
        })
        mae_client.logout()

        # No hay flujo en la UI para asignar el nivel todavía (gap conocido del
        # producto) — se asigna directo para variar los datos.
        profile = user.manager_profile
        profile.level = random.choice(['basico', 'intermedio', 'avanzado'])
        profile.level_assigned_at = timezone.now()
        profile.save()

    def _run_case_chat(self, user, mae, case, overdue):
        # Se crea la sesión directamente (mismo efecto que la vista start_case) para
        # poder asignar el caso específico que le toca en la rotación, en vez de
        # dejar que la vista elija uno al azar entre los no completados.
        session = CaseSession.objects.create(
            user=user, case=case, current_phase='ambiguity', status='en_progreso',
            priority=case.priority,
            sla_deadline=timezone.now() + timedelta(hours=case.sla_hours) if case.sla_hours else None,
        )
        if overdue:
            session.sla_deadline = timezone.now() - timedelta(hours=random.randint(2, 30))
            session.save(update_fields=['sla_deadline'])

        client = Client()
        client.force_login(user)

        for phase in ('ambiguity', 'pressure', 'dilemma'):
            answers = random.sample(PHASE_ANSWER_POOL[phase], 2)
            for text in answers:
                payload = self._telemetry()
                if random.random() < 0.35:
                    option = random.choice(list(QR_DISPLAY))
                    reason = random.choice(QUICK_REPLY_REASONS[option])
                    payload['message'] = f"{QR_DISPLAY[option]} — {reason}"
                    payload['quick_reply_option'] = option
                    payload['quick_reply_reason'] = reason
                else:
                    payload['message'] = text
                client.post(
                    reverse('send_message', args=[session.id]),
                    data=json.dumps(payload), content_type='application/json',
                )

        finish_payload = self._telemetry()
        finish_payload['message'] = 'Evaluar'
        client.post(
            reverse('send_message', args=[session.id]),
            data=json.dumps(finish_payload), content_type='application/json',
        )
        client.logout()

        mae_client = Client()
        mae_client.force_login(mae)
        mae_client.get(reverse('mae_review', args=[session.id]))  # completado -> en_validacion
        mae_client.post(reverse('mae_review', args=[session.id]), data={
            'mae_verdict': random.choice(CASE_VERDICTS),
            'mae_approved': 'true',
        })
        mae_client.logout()

        session.refresh_from_db()
        return session
