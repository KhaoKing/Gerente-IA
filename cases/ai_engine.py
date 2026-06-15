"""
Motor de IA — Gerente IA
Soporta múltiples proveedores de IA (Gemini, OpenAI y compatibles) mediante configuración
dinámica desde la BD (modelo AIConfiguration). Si no hay configuración activa, usa las
variables de entorno GEMINI_API_KEY / GEMINI_MODEL como fallback.
"""
import json
import random
import logging
import re
import urllib.request
import urllib.error
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Preguntas de diagnóstico ───────────────────────────────────────────────────

DIAGNOSIS_QUESTIONS = [
    {
        'number': 1,
        'text': (
            "Pregunta 1 de 5 — **Toma de decisiones**\n\n"
            "Uno de tus colaboradores clave comete un error grave que afecta a un cliente importante. "
            "El cliente exige una solución inmediata. Tienes 30 minutos para decidir. "
            "¿Qué haces primero y por qué?"
        )
    },
    {
        'number': 2,
        'text': (
            "Pregunta 2 de 5 — **Manejo de conflictos**\n\n"
            "Dos miembros de tu equipo tienen un conflicto personal que ya está afectando "
            "el trabajo del resto. Ambos son buenos colaboradores. "
            "¿Cómo lo manejas?"
        )
    },
    {
        'number': 3,
        'text': (
            "Pregunta 3 de 5 — **Delegación**\n\n"
            "Tienes un proyecto urgente pero tu agenda está saturada. "
            "Debes delegar la coordinación a alguien del equipo. "
            "¿Cómo eliges a quién delegar y qué le comunicas exactamente?"
        )
    },
    {
        'number': 4,
        'text': (
            "Pregunta 4 de 5 — **Comunicación y motivación**\n\n"
            "Tu equipo acaba de recibir una mala noticia: no habrá bonos este trimestre. "
            "El ambiente está tenso y notas desmotivación. "
            "¿Qué haces en las próximas 24 horas?"
        )
    },
    {
        'number': 5,
        'text': (
            "Pregunta 5 de 5 — **Visión y liderazgo**\n\n"
            "Tu director te pide presentar en 3 días un plan para mejorar el rendimiento "
            "del equipo en un 15% el próximo trimestre. "
            "¿Por dónde empiezas y qué incluirías en ese plan?"
        )
    },
]

DIAGNOSIS_ACK = [
    "Entendido. Pasemos a la siguiente situación.",
    "Gracias por tu respuesta. Continuamos.",
    "Anotado. Siguiente escenario.",
    "Bien, sigamos.",
]

# ── Respuestas de chatbox por categoría (fallback simulado) ───────────────────

CASE_RESPONSES = {
    'conflicto': [
        "Interesante enfoque. ¿Consideraste reunirte individualmente con cada parte antes de juntarlos? Eso permite entender los intereses de fondo de cada uno.",
        "Bien pensado. Un punto clave es separar las personas del problema. ¿Cómo describirías el conflicto sin mencionar a las personas involucradas?",
        "¿Qué necesita cada parte para sentirse escuchada? A veces el conflicto persiste porque alguien siente que su perspectiva no fue reconocida.",
    ],
    'comunicacion': [
        "La comunicación efectiva incluye confirmar que el mensaje fue recibido como fue enviado. ¿Cómo verificarías eso con tu equipo?",
        "¿Has mapeado los canales de comunicación informal en tu equipo? A veces la información crítica viaja por esos canales antes que por los formales.",
        "¿Qué barreras culturales u organizacionales podrían dificultar esa comunicación en la práctica?",
    ],
    'delegacion': [
        "Delegar no es solo asignar tareas, es transferir responsabilidad y autoridad. ¿Le diste al colaborador el nivel de autoridad necesario para decidir?",
        "¿Cómo harías el seguimiento sin microgestionar? El equilibrio entre control y autonomía es clave.",
        "¿Qué harías si el colaborador comete un error en la tarea delegada? La tolerancia al error es parte del proceso de delegación.",
    ],
    'motivacion': [
        "La motivación es individualizada — lo que motiva a uno puede desmotivar a otro. ¿Conoces las motivaciones particulares de cada miembro de tu equipo?",
        "Los reconocimientos públicos funcionan para algunos, pero otros prefieren el reconocimiento privado. ¿Cómo personalizarías tu enfoque?",
        "¿Cómo vincularías ese factor motivacional con el propósito del equipo para que tenga un impacto más duradero?",
    ],
    'decision': [
        "¿Identificaste todas las alternativas posibles o fuiste directo a la primera solución viable? Ampliar opciones suele mejorar las decisiones.",
        "Bajo presión, los gerentes tienden a decidir con poca información. ¿Qué dato crítico necesitarías para tener mayor confianza en esa decisión?",
        "¿Cómo involucrarías al equipo en esta decisión? La participación puede aumentar el compromiso con la ejecución.",
    ],
    'cambio': [
        "La resistencia al cambio es natural. ¿Cuál es la razón de fondo detrás de esa resistencia? ¿Miedo, pérdida de control, falta de información?",
        "Comunicar el 'por qué' del cambio antes del 'qué' y el 'cómo' reduce la resistencia. ¿Tienes clara esa narrativa?",
        "Los 'agentes de cambio' internos — personas respetadas que apoyan el cambio — son aliados clave. ¿Identificaste a alguno?",
    ],
}

# ── Respuestas a quick replies (fallback simulado) ────────────────────────────

QUICK_REPLY_RESPONSES = {
    'agree': [
        "Coincidimos, pero no te quedes ahí. {reason} Te reto: dame un escenario realista donde esa postura podría fallar y cómo lo prevendrías.",
        "Tomo nota de tu acuerdo. {reason} Ahora dime una acción concreta y medible que aplicarías en los próximos 7 días — con responsable, plazo y métrica.",
        "Bien, estamos alineados. {reason} ¿Qué riesgo no estás viendo? Identifica al menos uno que podría hacer que esta decisión salga mal.",
    ],
    'disagree': [
        "Tu desacuerdo es válido, pero exíjome sostener mi punto. {reason} ¿Qué evidencia concreta o experiencia previa respalda tu alternativa por encima de la mía?",
        "Entiendo que disientes. {reason} Compara los riesgos de tu enfoque versus el que propuse: ¿en qué escenario el tuyo falla y el mío no?",
        "Acepto el debate. {reason} Defiende tu posición con un ejemplo concreto — ¿cómo lo aplicarías paso a paso y qué pasaría si el equipo no responde como esperas?",
    ],
    'incomplete': [
        "Buen ojo, reconozco que falta algo. {reason} ¿Cuál es exactamente el elemento que echas en falta y por qué es crítico aquí?",
        "Tomo tu señalamiento. {reason} Dime cómo integrarías ese elemento faltante en una acción medible — sin eso, queda solo en observación.",
        "Correcto, hay aspectos que no abordé. {reason} Prioriza: de lo que falta, ¿qué resolverías en las primeras 48 horas y qué dejarías para después?",
    ],
}

FINISH_TRIGGERS = ['listo', 'terminar', 'evaluar', 'finalizar', 'fin', 'concluir', 'termino', 'terminé']

# ── System prompts por fase ────────────────────────────────────────────────────

PHASE_SYSTEM_PROMPTS = {
    'ambiguity': (
        "Estás en la **Fase 1 — Ambigüedad** del caso. Tu objetivo: "
        "detectar un punto ciego en el razonamiento del gerente y advertirle sobre "
        "una variable crítica que no está considerando. NO des la solución. "
        "Haz preguntas que lo obliguen a identificar la información faltante. "
        "Sostén la fase hasta que el gerente demuestre haber identificado el punto ciego."
    ),
    'pressure': (
        "Estás en la **Fase 2 — Presión**. El gerente ya identificó un punto ciego. "
        "Ahora introduce un agravante externo e inesperado que requiera acción táctica "
        "inmediata. Reduce su margen de maniobra. Ejemplos: un cliente amenaza con irse, "
        "un recorte presupuestal de última hora, una renuncia inesperada en el equipo. "
        "Mantén la presión hasta que el gerente proponga una acción táctica concreta."
    ),
    'dilemma': (
        "Estás en la **Fase 3 — El Dilema**. El gerente ya enfrentó la presión. "
        "Ahora propón una solución altamente eficiente para el problema, pero que "
        "implique un riesgo ético, reputacional o de fricción cultural para la organización. "
        "Ejemplos: despedir a un empleado de bajo rendimiento que es muy querido, "
        "ocultar información a un cliente para ganar tiempo, saltar un proceso interno "
        "para salvar el proyecto. Evalúa cómo el gerente negocia este límite."
    ),
}

PHASE_LABELS = {
    'ambiguity': 'Fase 1 — Ambigüedad',
    'pressure': 'Fase 2 — Presión',
    'dilemma': 'Fase 3 — Dilema',
    'completed': 'Fases Completadas',
}


# ── Validación de respuestas del usuario ──────────────────────────────────────

_GIBBERISH_RE = re.compile(r'^[a-z0-9]{5,}$', re.IGNORECASE)
_VOWELS = set('aeiouáéíóúü')


def validate_user_message(message: str) -> tuple[bool, str]:
    """
    Valida que el mensaje del usuario sea coherente y no sea ruido tipo "cnasooq1".
    Retorna (es_valido, razon_si_invalido).
    """
    if not message:
        return False, "El mensaje está vacío. Por favor escribe tu respuesta."

    text = message.strip()

    # Largo mínimo razonable para una reflexión gerencial
    if len(text) < 10:
        return False, (
            "Tu respuesta es muy corta para evaluarla. "
            "Por favor desarrolla tu idea con al menos una oración completa que explique qué harías y por qué."
        )

    # Debe contener al menos 2 palabras (con espacios reales)
    words = [w for w in re.split(r'\s+', text) if w]
    if len(words) < 3:
        return False, (
            "Necesito un poco más de detalle. Escribe tu respuesta en una oración completa "
            "(al menos 3 palabras) describiendo qué harías y por qué."
        )

    # Si parece una sola cadena alfanumérica sin estructura → ruido (ej. "cnasooq1")
    no_spaces = text.replace(' ', '')
    if _GIBBERISH_RE.match(no_spaces) and ' ' not in text:
        return False, (
            "No entendí tu respuesta. Parece un texto al azar. "
            "Por favor responde con frases reales explicando tu razonamiento gerencial."
        )

    # Proporción de vocales — texto real en español ronda 35-45% vocales sobre letras
    letters = [c for c in text.lower() if c.isalpha()]
    if letters:
        vowel_ratio = sum(1 for c in letters if c in _VOWELS) / len(letters)
        if vowel_ratio < 0.18:
            return False, (
                "Tu mensaje no parece tener palabras reales. "
                "Reescríbelo con oraciones que describan cómo manejarías la situación."
            )

    # Secuencias muy largas de consonantes consecutivas → gibberish
    if re.search(r'[bcdfghjklmnñpqrstvwxyz]{6,}', text.lower()):
        return False, (
            "Hay partes de tu mensaje que no se entienden. "
            "Por favor revisa lo que escribiste y respóndeme con frases claras."
        )

    return True, ""


# ── Conexión a IA (configuración dinámica) ─────────────────────────────────────


def _get_active_config():
    """Retorna la configuración activa desde BD. Si no hay, retorna None."""
    from .models import AIConfiguration
    return AIConfiguration.get_active()


def _ai_available() -> bool:
    """Hay IA disponible? (configuración BD o fallback de settings)."""
    config = _get_active_config()
    if config and config.api_url and config.api_key:
        return True
    return bool(getattr(settings, 'GEMINI_API_KEY', '').strip())


def _call_ai_api(system_prompt: str, user_prompt: str) -> str:
    """
    Llama a la API de IA configurada (BD o fallback Gemini de settings).
    Detecta automáticamente el formato (Gemini vs OpenAI-compatible).
    Lanza excepción si falla — el llamador decide el fallback.
    """
    config = _get_active_config()

    if config and config.api_url and config.api_key:
        api_url = config.api_url
        api_key = config.api_key
        provider = config.provider
        model = config.model_name or 'default'
    else:
        # Fallback a settings (Gemini)
        api_key = settings.GEMINI_API_KEY.strip()
        model = getattr(settings, 'GEMINI_MODEL', 'gemini-3.5-flash')
        api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        provider = 'gemini'

    return _call_api_internal(api_url, api_key, provider, model, system_prompt, user_prompt)


def _call_api_internal(api_url: str, api_key: str, provider: str, model: str,
                       system_prompt: str, user_prompt: str) -> str:
    """Ejecuta la llamada HTTP a la API según el proveedor."""
    if provider == 'gemini' or 'generativelanguage' in api_url:
        return _call_gemini_format(api_url, system_prompt, user_prompt)
    else:
        # Todos los proveedores OpenAI-compatible (openai, deepseek, groq, mistral, together, etc.)
        return _call_openai_format(api_url, api_key, model, system_prompt, user_prompt)


def _call_gemini_format(url: str, system_prompt: str, user_prompt: str) -> str:
    """Formato Gemini: system_instruction + contents."""
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500},
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode('utf-8')
    data = json.loads(body)
    candidates = data.get('candidates') or []
    if not candidates:
        raise RuntimeError(f"API no devolvió candidatos: {data}")
    parts = candidates[0].get('content', {}).get('parts', [])
    text = ''.join(p.get('text', '') for p in parts).strip()
    if not text:
        raise RuntimeError("API devolvió respuesta vacía.")
    return text


def _call_openai_format(url: str, api_key: str, model: str,
                        system_prompt: str, user_prompt: str) -> str:
    """Formato OpenAI-compatible: messages array con roles."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }, method='POST',
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode('utf-8')
    data = json.loads(body)
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError(f"API no devolvió choices: {data}")
    text = choices[0].get('message', {}).get('content', '').strip()
    if not text:
        raise RuntimeError("API devolvió respuesta vacía.")
    return text


# ── Diagnóstico ───────────────────────────────────────────────────────────────

def get_diagnosis_response(question_number: int, user_answer: str, is_last: bool) -> str:
    """Respuesta de la IA durante el diagnóstico.
    Si la IA está disponible, genera preguntas dinámicas basadas en las respuestas previas
    para profundizar en el nivel real del gerente."""
    if is_last:
        if _ai_available():
            try:
                system = (
                    "Eres un MAE experto en competencias gerenciales. "
                    "Acabas de terminar un diagnóstico de 5 preguntas situacionales con un gerente. "
                    "Responde brevemente (máx 4 oraciones) agradeciendo, indicando que has analizado sus respuestas "
                    "y que su MAE humano revisará el diagnóstico para confirmar el nivel asignado. "
                    "Responde siempre en español, sin emojis."
                )
                user = f"Última respuesta del gerente: {user_answer}\nGenera el cierre del diagnóstico."
                return _call_ai_api(system, user)
            except Exception as e:
                logger.error(f"IA falló en cierre diagnóstico: {e}")
        return (
            "Gracias por completar el diagnóstico. He analizado tus respuestas.\n\n"
            "En breve recibirás tu nivel asignado y tu ruta de capacitación personalizada. "
            "Tu MAE revisará este diagnóstico antes de confirmar el resultado."
        )

    # Generar siguiente pregunta — dinámica con IA, o fallback a pregunta fija
    topic = DIAGNOSIS_QUESTIONS[question_number]
    if _ai_available():
        try:
            prev_topic = DIAGNOSIS_QUESTIONS[question_number - 1]
            system = (
                "Eres un evaluador experto en competencias gerenciales realizando un diagnóstico. "
                "El gerente acaba de responder una pregunta situacional. Tu tarea es doble:\n\n"
                "1. Genera UNA SOLA oración breve de acuse (máx 15 palabras), neutra, sin valorar, en español.\n"
                "2. Luego, basándote en la respuesta del gerente, formula UNA pregunta de seguimiento "
                "que profundice en el tema '{topic}' y que te permita evaluar mejor su nivel real. "
                "La pregunta debe ser abierta, situacional y obligarlo a explicar su razonamiento. "
                "No repitas la pregunta original — adáptala a lo que el gerente ya respondió.\n\n"
                "Formato de respuesta:\n"
                "[Acuse]\n\n"
                "[Pregunta de seguimiento]\n\n"
                "Sin emojis. Sin valorar la respuesta previa."
            ).replace('{topic}', topic['text'].split('**')[1] if '**' in topic['text'] else 'competencias gerenciales')
            user = (
                f"Pregunta anterior ({prev_topic['text'].split(chr(10))[0]}): {prev_topic['text']}\n\n"
                f"Respuesta del gerente: {user_answer}\n\n"
                f"Genera el acuse y la siguiente pregunta de diagnóstico."
            )
            return _call_ai_api(system, user)
        except Exception as e:
            logger.error(f"IA falló en pregunta dinámica diagnóstico: {e}")

    ack = random.choice(DIAGNOSIS_ACK)
    return f"{ack}\n\n{topic['text']}"


# ── Chatbox de casos ──────────────────────────────────────────────────────────

def _build_case_history(session, limit: int = 12) -> list[dict]:
    """Construye historial de mensajes para enviar como contexto a la IA."""
    msgs = list(session.messages.order_by('-created_at')[:limit])
    msgs.reverse()
    history = []
    for m in msgs:
        role = "user" if m.role == "user" else "model"
        history.append({"role": role, "parts": [{"text": m.content}]})
    return history


def _call_ai_api_with_history(system_prompt: str, history: list[dict], new_user_text: str) -> str:
    """Variante con historial multi-turno."""
    config = _get_active_config()

    if config and config.api_url and config.api_key:
        api_url = config.api_url
        api_key = config.api_key
        provider = config.provider
        model = config.model_name or 'default'
    else:
        api_key = settings.GEMINI_API_KEY.strip()
        model = getattr(settings, 'GEMINI_MODEL', 'gemini-3.5-flash')
        api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        provider = 'gemini'

    if provider == 'gemini' or 'generativelanguage' in api_url:
        contents = list(history)
        contents.append({"role": "user", "parts": [{"text": new_user_text}]})
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500},
        }
        req = urllib.request.Request(
            api_url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8')
        data = json.loads(body)
        candidates = data.get('candidates') or []
        if not candidates:
            raise RuntimeError(f"API no devolvió candidatos: {data}")
        parts = candidates[0].get('content', {}).get('parts', [])
        text = ''.join(p.get('text', '') for p in parts).strip()
        if not text:
            raise RuntimeError("API devolvió respuesta vacía.")
        return text
    else:
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            content = h.get("parts", [{}])[0].get("text", "")
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": new_user_text})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500,
        }
        req = urllib.request.Request(
            api_url, data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            }, method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8')
        data = json.loads(body)
        choices = data.get('choices') or []
        if not choices:
            raise RuntimeError(f"API no devolvió choices: {data}")
        text = choices[0].get('message', {}).get('content', '').strip()
        if not text:
            raise RuntimeError("API devolvió respuesta vacía.")
        return text


def _should_advance_phase(session) -> bool:
    """Retorna True si el usuario ya ha respondido suficientes veces en la fase actual."""
    msgs = session.messages.filter(role='user')
    # Contamos mensajes del usuario desde que empezó la fase actual
    phase_start = session.messages.filter(
        role='assistant', message_type='system_info'
    ).filter(content__contains=PHASE_LABELS.get(session.current_phase, '')).last()
    if phase_start:
        msgs_in_phase = msgs.filter(created_at__gt=phase_start.created_at).count()
    else:
        msgs_in_phase = msgs.count()
    return msgs_in_phase >= 2


def _build_phase_prompt(case, session, quick_reply_option='', quick_reply_reason='') -> str:
    """Construye el system prompt según la fase actual, incluyendo contexto del nivel del gerente."""
    phase = session.current_phase
    phase_instruction = PHASE_SYSTEM_PROMPTS.get(phase, "")

    # Contexto del nivel del gerente (diagnóstico)
    level_context = ""
    try:
        profile = session.user.manager_profile
        if profile.level != 'sin_nivel':
            level_context = (
                f"\n\nEl gerente fue evaluado con nivel '{profile.get_level_display()}' "
                f"en competencias gerenciales. Ajusta la profundidad y exigencia de tus "
                f"preguntas y retos a ese nivel."
            )
            # Incluir dictamen del MAE si existe
            try:
                d_session = session.user.diagnosis_session
                if d_session and d_session.mae_verdict:
                    level_context += (
                        f" Observaciones del MAE sobre el gerente: {d_session.mae_verdict}"
                    )
            except Exception:
                pass
    except Exception:
        pass

    qr_directive = ""
    if quick_reply_option:
        directives = {
            'agree': (
                "El gerente está de acuerdo con tu reflexión anterior. NO simplemente lo felicites. "
                "Reconoce brevemente su acuerdo y CONTRA-RESPONDE retándolo: presenta un escenario "
                "donde su postura podría fallar, pídele un riesgo concreto que no haya considerado, "
                "o exígele una acción medible para los próximos 7 días."
            ),
            'disagree': (
                "El gerente NO está de acuerdo con tu reflexión anterior. NO cedas de inmediato. "
                "CONTRA-RESPONDE: defiende con un argumento concreto la postura cuestionada, "
                "pídele evidencia o un ejemplo que respalde su alternativa, y compara los riesgos "
                "de ambas posiciones antes de cerrar con una pregunta que lo obligue a sustentar más."
            ),
            'incomplete': (
                "El gerente afirma que falta un elemento en el análisis. CONTRA-RESPONDE así: "
                "valida brevemente que su observación es relevante, identifica qué elemento concreto "
                "él está señalando, y devuélvele una pregunta puntual sobre cómo integraría ese "
                "elemento faltante en una acción medible."
            ),
        }
        qr_directive = "\n" + directives.get(quick_reply_option, "")

    return (
        "Eres un MAE gerencial experto que entrena gerentes mediante casos situacionales. "
        f"El caso actual es: '{case.title}' (categoría: {case.get_category_display()}, "
        f"dificultad: {case.get_difficulty_display()}).\n"
        f"Descripción del caso: {case.description}\n"
        f"{level_context}\n"
        f"{phase_instruction}\n\n"
        "Habla en español, tono respetuoso, sin emojis. "
        "No des recetas; haz preguntas que lo hagan pensar. "
        "Si el gerente quiere finalizar, escribirá 'evaluar'."
        + qr_directive
    )


def get_ai_response(user_message: str, session, case, quick_reply_option: str = '', quick_reply_reason: str = '') -> tuple[str, bool]:
    """
    Genera respuesta de la IA para el chatbox de casos.
    Retorna (mensaje, hubo_error).
    """
    try:
        msg_lower = user_message.lower()

        if any(t in msg_lower for t in FINISH_TRIGGERS):
            return generate_final_feedback(session), False

        # Modo Gemini
        if _ai_available():
            try:
                qr_hint = ""
                if quick_reply_option:
                    labels = {
                        'agree': "El gerente seleccionó el botón 'Estoy de acuerdo'.",
                        'disagree': "El gerente seleccionó el botón 'No estoy de acuerdo'.",
                        'incomplete': "El gerente seleccionó el botón 'Creo que falta algo'.",
                    }
                    qr_hint = (
                        f"\n\nSeñal del gerente vía botón: {labels.get(quick_reply_option, '')} "
                        f"Razón aportada por él: '{quick_reply_reason}'."
                    )

                system = _build_phase_prompt(case, session, quick_reply_option, quick_reply_reason)
                history = _build_case_history(session)
                if history and history[-1]["role"] == "user":
                    last_user_text = history[-1]["parts"][0]["text"]
                    history = history[:-1]
                    return _call_ai_api_with_history(system, history, last_user_text + qr_hint), False
                return _call_ai_api_with_history(system, history, user_message + qr_hint), False
            except Exception as e:
                logger.error(f"Gemini falló en chat de caso, usando fallback: {e}")

        # Fallback simulado por fase
        phase = session.current_phase
        fallbacks = {
            'ambiguity': [
                "Tu enfoque tiene mérito, pero hay una variable que no estás considerando. "
                "¿Qué pasaría si el contexto externo cambiara drásticamente?",
                "Detente un momento. La información que tienes es incompleta. "
                "¿Qué dato crucial te falta para tomar una decisión informada?",
            ],
            'pressure': [
                "Acaba de llegar una noticia: un cliente clave amenaza con cancelar el contrato "
                "si no hay una solución en 48 horas. ¿Qué haces ahora?",
                "Presupuesto recortado un 20% efectivo inmediato. Tu mejor colaborador renunció. "
                "¿Cómo reaccionas tácticamente?",
            ],
            'dilemma': [
                "Podrías resolver esto rápidamente si aceptas saltar un proceso interno. "
                "Nadie se enteraría, pero va contra la política de la empresa. ¿Lo harías?",
                "La solución más eficiente es reasignar a un empleado a un puesto que no quiere, "
                "pero es lo mejor para el equipo. ¿Cómo manejas la fricción?",
            ],
        }
        phase_fallbacks = fallbacks.get(phase, [])
        if phase_fallbacks:
            return random.choice(phase_fallbacks), False

        if quick_reply_option:
            templates = QUICK_REPLY_RESPONSES.get(quick_reply_option, [])
            if templates:
                template = random.choice(templates)
                reason_text = f"Mencionas que: *'{quick_reply_reason}'*." if quick_reply_reason else ""
                return template.format(reason=reason_text), False

        responses = CASE_RESPONSES.get(case.category, [
            "Reflexiona: ¿tu decisión considera tanto el corto como el largo plazo?",
            "¿Cómo medirías el éxito de esa acción? Un gerente efectivo define métricas claras.",
        ])
        return random.choice(responses), False

    except Exception as e:
        logger.error(f"Error en motor IA: {e}")
        return "", True  # señal de error


def generate_final_feedback(session) -> str:
    """Retroalimentación final al cerrar un caso. Usa IA si está disponible."""
    count = session.messages.filter(role='user').count()

    # Contexto del nivel del gerente
    level_note = ""
    try:
        profile = session.user.manager_profile
        if profile.level != 'sin_nivel':
            level_note = (
                f"\nEl gerente tiene nivel '{profile.get_level_display()}' "
                f"según su diagnóstico. Considera este nivel al evaluar sus respuestas."
            )
    except Exception:
        pass

    if _ai_available():
        try:
            history = _build_case_history(session, limit=30)
            transcript = "\n".join(
                f"{('Gerente' if h['role']=='user' else 'MAE IA')}: {h['parts'][0]['text']}"
                for h in history
            )
            system = (
                "Eres un MAE gerencial. A continuación tienes la transcripción de una sesión de caso. "
                "Genera una retroalimentación final breve (4-6 oraciones, en español, sin emojis) que: "
                "(1) reconozca lo que el gerente analizó bien, (2) señale uno o dos puntos a profundizar, "
                "(3) recuerde que su MAE humano revisará la sesión y emitirá el dictamen final."
                + level_note
            )
            return _call_ai_api(system, f"Transcripción de la sesión:\n{transcript}")
        except Exception as e:
            logger.error(f"IA falló en feedback final: {e}")

    if count < 3:
        return (
            "Has dado respuestas iniciales, pero un análisis gerencial robusto "
            "requiere explorar más ángulos. Te recomiendo profundizar más en próximos casos.\n\n"
            "Tu sesión quedó guardada y será revisada por tu MAE."
        )
    return (
        f"Has completado este caso con {count} intervenciones. "
        "Demostraste capacidad analítica y disposición reflexiva. "
        "Tu MAE revisará esta sesión y emitirá el dictamen final antes de registrar tu resultado."
    )


def get_ia_error_message() -> str:
    return (
        "⚠️ El servicio de IA no está disponible en este momento. "
        "Tu mensaje fue guardado y tu sesión está protegida. "
        "El administrador ha sido notificado automáticamente. "
        "Por favor intenta de nuevo en unos minutos."
    )


def notify_admin_ia_error(user, session, error_detail: str):
    """Registra el error en BD y notifica al admin."""
    from cases.models import IAErrorLog
    from django.core.mail import send_mail
    from django.conf import settings as conf

    IAErrorLog.objects.create(
        user=user,
        session=session,
        error_type='ia_unavailable',
        error_detail=error_detail,
        notified_admin=True,
    )

    try:
        send_mail(
            subject=f'[Gerente IA] Error de IA — Usuario: {user.username}',
            message=(
                f"Se produjo un error en el motor de IA.\n\n"
                f"Usuario: {user.get_full_name()} ({user.username})\n"
                f"Sesión ID: {session.id if session else 'N/A'}\n"
                f"Detalle: {error_detail}"
            ),
            from_email='sistema@gerenteIA.com',
            recipient_list=[conf.ADMIN_EMAIL],
            fail_silently=True,
        )
    except Exception:
        pass
