import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage, IAErrorLog, AIConfiguration
from .ai_engine import (
    get_ai_response, get_diagnosis_response, get_ia_error_message,
    notify_admin_ia_error, DIAGNOSIS_QUESTIONS, FINISH_TRIGGERS,
    validate_user_message, _should_advance_phase, PHASE_LABELS,
)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    if user.is_gerente:
        # Estado del diagnóstico — define qué hace el botón único del dashboard
        # Estados posibles: 'no_iniciado', 'en_progreso', 'esperando_mae', 'aprobado', 'rechazado'
        diagnosis_state = 'no_iniciado'
        diagnosis_session = None
        try:
            diagnosis_session = user.diagnosis_session
            if diagnosis_session.status == 'en_progreso':
                diagnosis_state = 'en_progreso'
            elif diagnosis_session.status == 'rechazado':
                diagnosis_state = 'rechazado'
            elif diagnosis_session.mae_approved is True or diagnosis_session.status in ('aprobado', 'nivel_asignado'):
                diagnosis_state = 'aprobado'
            elif diagnosis_session.status == 'completado':
                diagnosis_state = 'esperando_mae'
        except DiagnosisSession.DoesNotExist:
            diagnosis_state = 'no_iniciado'

        active_session = CaseSession.objects.filter(
            user=user, status='en_progreso'
        ).select_related('case').first()

        completed_sessions = CaseSession.objects.filter(
            user=user, status__in=['completado', 'en_revision', 'evaluado']
        ).select_related('case').order_by('-completed_at')[:5]

        context.update({
            'diagnosis_state': diagnosis_state,
            'diagnosis_session': diagnosis_session,
            'active_session': active_session,
            'completed_sessions': completed_sessions,
            'available_cases': ManagementCase.objects.filter(is_active=True).count(),
        })

    elif user.is_mae:
        from accounts.models import User as UserModel
        from django.db.models import Avg, Count, Max, Min

        # Diagnósticos completados esperando validación del MAE
        pending_diagnoses = DiagnosisSession.objects.filter(
            status='completado'
        ).select_related('user').order_by('-completed_at')

        # Sesiones de caso pendientes de revisión
        pending_reviews = CaseSession.objects.filter(
            status='completado'
        ).select_related('user', 'case').order_by('-completed_at')

        in_review = CaseSession.objects.filter(
            mae=user, status='en_revision'
        ).select_related('user', 'case')
        all_manager_sessions = CaseSession.objects.select_related('user', 'case').order_by('-started_at')

        managers_list = UserModel.objects.filter(role='gerente').prefetch_related('manager_profile')

        # ── Métricas de tiempos de respuesta ──
        response_metrics = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).aggregate(
            avg_response=Avg('response_time_seconds'),
            max_response=Max('response_time_seconds'),
            avg_pause=Avg('total_pause_seconds'),
        )

        # Métricas finas de telemetría (ms)
        fine_metrics = ChatMessage.objects.filter(
            role='user', latency_reading_ms__isnull=False
        ).aggregate(
            avg_reading=Avg('latency_reading_ms'),
            avg_execution=Avg('latency_execution_ms'),
            avg_backspaces=Avg('backspace_count'),
        )

        # Top gerentes por tiempo de respuesta promedio
        user_metrics_raw = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).values(
            'session__user_id', 'session__user__first_name', 'session__user__last_name'
        ).annotate(
            avg_response=Avg('response_time_seconds'),
            avg_pause=Avg('total_pause_seconds'),
            total_messages=Count('id'),
            last_msg=Max('created_at'),
        ).order_by('avg_response')[:10]

        user_metrics = []
        for m in user_metrics_raw:
            avg_r = m['avg_response'] or 0
            avg_p = m['avg_pause'] or 0
            user_metrics.append({
                'user_id': m['session__user_id'],
                'name': f"{m['session__user__first_name']} {m['session__user__last_name']}".strip(),
                'avg_response': avg_r,
                'avg_pause': avg_p,
                'total_messages': m['total_messages'],
                'efficiency': round((avg_r - avg_p) / max(avg_r, 1) * 100, 1) if avg_r > 0 else 0,
            })

        # ── Datos para gráfico NChs ──
        nchs_sessions = CaseSession.objects.filter(
            n_interactions__gt=0
        ).select_related('user').order_by('-nchs_score')

        nchs_aggregate = CaseSession.objects.filter(
            n_interactions__gt=0
        ).aggregate(
            avg_nchs=Avg('nchs_score'),
            max_nchs=Max('nchs_score'),
            min_nchs=Min('nchs_score'),
        )

        # Clasificaciones por tipo
        classification_counts = ChatMessage.objects.filter(
            classification_variable__isnull=False
        ).values('classification_variable').annotate(count=Count('id'))
        class_data = {c['classification_variable']: c['count'] for c in classification_counts}

        # Sesiones abandonadas
        abandoned_sessions = CaseSession.objects.filter(
            status='abandoned'
        ).select_related('user').order_by('-last_heartbeat')

        total_measured = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).count()

        context.update({
            'pending_diagnoses': pending_diagnoses,
            'pending_reviews': pending_reviews,
            'in_review': in_review,
            'all_sessions': all_manager_sessions,
            'managers_list': managers_list,
            'response_metrics': response_metrics,
            'fine_metrics': fine_metrics,
            'user_metrics': user_metrics,
            'total_measured_messages': total_measured,
            'nchs_sessions': nchs_sessions,
            'nchs_aggregate': nchs_aggregate,
            'class_data': class_data,
            'abandoned_sessions': abandoned_sessions,
        })

    elif user.is_admin_role:
        from accounts.models import User as UserModel

        ia_errors = IAErrorLog.objects.order_by('-created_at')[:10]
        ai_config = AIConfiguration.get_active()
        context.update({
            'total_users': UserModel.objects.count(),
            'total_managers': UserModel.objects.filter(role='gerente').count(),
            'total_maes': UserModel.objects.filter(role='mae').count(),
            'total_cases': ManagementCase.objects.count(),
            'active_sessions': CaseSession.objects.filter(status='en_progreso').count(),
            'pending_reviews': CaseSession.objects.filter(status='completado').count(),
            'ia_errors': ia_errors,
            'ai_config': ai_config,
        })

    return render(request, 'cases/dashboard.html', context)


# ── Configuración de API ───────────────────────────────────────────────────────

@login_required
def api_config(request):
    from django.contrib.auth.decorators import user_passes_test
    if not request.user.is_admin_role:
        return redirect('dashboard')

    ai_config = AIConfiguration.get_active()

    if request.method == 'POST' and 'save_api_config' in request.POST:
        provider = request.POST.get('provider', 'openai_compatible')
        api_url = request.POST.get('api_url', '').strip()
        api_key = request.POST.get('api_key', '').strip()
        model_name = request.POST.get('model_name', '').strip()

        if api_url and api_key:
            AIConfiguration.objects.all().update(is_active=False)
            AIConfiguration.objects.create(
                name='Configuracion Principal',
                provider=provider,
                api_url=api_url,
                api_key=api_key,
                model_name=model_name,
                is_active=True,
            )
            from django.contrib import messages
            messages.success(request, 'Configuracion de IA guardada correctamente.')
        else:
            from django.contrib import messages
            messages.error(request, 'La URL y la API Key son obligatorias.')
        return redirect('api_config')

    return render(request, 'cases/api_config.html', {'ai_config': ai_config})


# ── Diagnóstico ────────────────────────────────────────────────────────────────

@login_required
def start_diagnosis(request):
    if not request.user.is_gerente:
        return redirect('dashboard')

    # Si ya existe sesión, manejar según su estado
    try:
        session = request.user.diagnosis_session
        if session.status == 'en_progreso':
            return redirect('diagnosis_chat')
        if session.status == 'rechazado':
            # El MAE rechazó: reiniciamos el diagnóstico reusando la misma sesión
            session.messages.all().delete()
            session.status = 'en_progreso'
            session.current_question = 1
            session.mae_approved = None
            session.mae_verdict = ''
            session.mae_reviewed_at = None
            session.completed_at = None
            session.save()
            # También reseteamos la bandera del perfil
            try:
                profile = request.user.manager_profile
                profile.diagnosis_completed = False
                profile.save()
            except Exception:
                pass
            first_q = DIAGNOSIS_QUESTIONS[0]
            DiagnosisMessage.objects.create(
                session=session, role='assistant',
                content=(
                    "Vamos a repetir el diagnóstico según indicó tu MAE.\n\n"
                    "Responde con frases completas y describe claramente qué harías y por qué.\n\n"
                    "---\n\n"
                    f"{first_q['text']}"
                ),
                question_number=1,
            )
            return redirect('diagnosis_chat')
        if session.mae_approved is True or session.status in ('aprobado', 'nivel_asignado'):
            # Ya aprobado: no se reinicia
            return redirect('dashboard')
        if session.status == 'completado':
            # Esperando MAE
            return redirect('dashboard')
    except DiagnosisSession.DoesNotExist:
        pass

    # Crear sesión nueva
    session = DiagnosisSession.objects.create(user=request.user)
    # Primer mensaje de bienvenida + primera pregunta
    first_q = DIAGNOSIS_QUESTIONS[0]
    DiagnosisMessage.objects.create(
        session=session, role='assistant',
        content=(
            "¡Hola! Soy tu MAE IA.\n\n"
            "Antes de comenzar tu programa de capacitación, necesito conocer tu nivel "
            "gerencial actual. Te haré **5 preguntas situacionales** — no hay respuestas "
            "correctas o incorrectas, solo quiero entender cómo piensas y decides.\n\n"
            "Tómate el tiempo que necesites en cada respuesta.\n\n"
            "---\n\n"
            f"{first_q['text']}"
        ),
        question_number=1,
    )
    return redirect('diagnosis_chat')


@login_required
def diagnosis_chat(request):
    try:
        session = request.user.diagnosis_session
    except DiagnosisSession.DoesNotExist:
        return redirect('start_diagnosis')
    chat_messages = session.messages.all()
    return render(request, 'cases/diagnosis_chat.html', {'session': session, 'chat_messages': chat_messages})


@login_required
@require_POST
def diagnosis_send(request):
    try:
        session = request.user.diagnosis_session
    except DiagnosisSession.DoesNotExist:
        return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

    if session.status != 'en_progreso':
        return JsonResponse({'error': 'El diagnóstico ya fue completado.'}, status=400)

    data = json.loads(request.body)
    user_message = data.get('message', '').strip()
    if not user_message:
        return JsonResponse({'error': 'Mensaje vacío.'}, status=400)

    # Validar que la respuesta tenga sentido (rechazar gibberish tipo "cnasooq1")
    is_valid, reason = validate_user_message(user_message)
    if not is_valid:
        return JsonResponse({
            'response': reason,
            'is_invalid_input': True,
            'session_status': session.status,
            'question_number': session.current_question,
            'timestamp': timezone.now().strftime('%H:%M'),
        })

    current_q = session.current_question

    # Guardar respuesta del usuario
    DiagnosisMessage.objects.create(
        session=session, role='user',
        content=user_message, question_number=current_q,
    )

    is_last = current_q >= 5

    if is_last:
        # Diagnóstico completo
        ai_text = get_diagnosis_response(current_q, user_message, is_last=True)
        DiagnosisMessage.objects.create(session=session, role='assistant', content=ai_text)
        session.status = 'completado'
        session.completed_at = timezone.now()
        session.save()

        # Marcar perfil como diagnóstico completado (nivel se asigna cuando el MAE lo revise)
        try:
            profile = request.user.manager_profile
            profile.diagnosis_completed = True
            profile.save()
        except Exception:
            pass

        return JsonResponse({
            'response': ai_text,
            'session_status': 'completado',
            'timestamp': timezone.now().strftime('%H:%M'),
        })
    else:
        # Avanzar a siguiente pregunta
        session.current_question = current_q + 1
        session.save()
        ai_text = get_diagnosis_response(current_q, user_message, is_last=False)
        DiagnosisMessage.objects.create(
            session=session, role='assistant',
            content=ai_text, question_number=current_q + 1,
        )
        return JsonResponse({
            'response': ai_text,
            'session_status': 'en_progreso',
            'question_number': session.current_question,
            'timestamp': timezone.now().strftime('%H:%M'),
        })


# ── Casos gerenciales ──────────────────────────────────────────────────────────

@login_required
def start_case(request):
    # Los gerentes solo pueden iniciar caso con la IA si su diagnóstico ya fue
    # aprobado por el MAE. Antes de eso, su único botón disponible es el del
    # diagnóstico inicial (5 preguntas).
    if request.user.is_gerente:
        try:
            d_session = request.user.diagnosis_session
        except DiagnosisSession.DoesNotExist:
            return redirect('start_diagnosis')
        if not (d_session.mae_approved is True or d_session.status in ('aprobado', 'nivel_asignado')):
            return redirect('dashboard')

    completed_ids = CaseSession.objects.filter(
        user=request.user, status__in=['completado', 'en_revision', 'evaluado']
    ).values_list('case_id', flat=True)

    # Filtrar por nivel del gerente si ya tiene uno asignado
    level_filter = {}
    try:
        profile = request.user.manager_profile
        if profile.level != 'sin_nivel':
            level_filter = {'difficulty': profile.level}
    except Exception:
        pass

    case = ManagementCase.objects.filter(
        is_active=True, **level_filter
    ).exclude(id__in=completed_ids).order_by('?').first()

    # Fallback: cualquier caso disponible
    if not case:
        case = ManagementCase.objects.filter(is_active=True).order_by('?').first()

    if not case:
        return redirect('dashboard')

    session = CaseSession.objects.create(user=request.user, case=case, current_phase='ambiguity')
    ChatMessage.objects.create(
        session=session, role='assistant',
        content=(
            f"**Caso: {case.title}**\n\n"
            f"{case.description}\n\n"
            "---\n"
            "**Fase 1 — Ambigüedad**\n\n"
            "Has leído el caso. Antes de lanzarte a una solución, detecta un punto ciego: "
            "hay una variable crítica que no estás considerando. "
            "¿Cuál es? No te pido la solución aún, solo que identifiques qué información "
            "clave falta o qué ángulo del problema estás ignorando."
        ),
        message_type='system_info',
    )
    return redirect('pre_evaluation', session_id=session.id)


@login_required
def chat_view(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)

    # Si la sesión está completada y no tiene post-autopsia, redirigir
    if session.status in ('completado', 'en_revision') and not hasattr(session, 'post_autopsy'):
        return redirect('post_autopsy', session_id=session.id)

    chat_messages = session.messages.all()
    last_ai_msg = chat_messages.filter(role='assistant').last()
    phase_label = dict(CaseSession.PHASE_CHOICES).get(session.current_phase, '')
    context = {
        'session': session, 'chat_messages': chat_messages, 'case': session.case,
        'last_ai_timestamp': last_ai_msg.created_at.isoformat() if last_ai_msg else '',
        'current_phase_label': phase_label,
    }
    return render(request, 'cases/chat.html', context)


@login_required
@require_POST
def send_message(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)

    if session.status != 'en_progreso':
        return JsonResponse({'error': 'Esta sesión ya ha finalizado.'}, status=400)

    data = json.loads(request.body)
    user_message = data.get('message', '').strip()
    quick_reply_option = data.get('quick_reply_option', '')
    quick_reply_reason = data.get('quick_reply_reason', '').strip()
    response_time = data.get('response_time_seconds')
    total_pause = data.get('total_pause_seconds')
    latency_reading = data.get('latency_reading_ms')
    latency_execution = data.get('latency_execution_ms')
    backspace_count = data.get('backspace_count')

    if not user_message:
        return JsonResponse({'error': 'Mensaje vacío.'}, status=400)

    # Validar coherencia del mensaje
    msg_lower = user_message.lower()
    if not any(t in msg_lower for t in FINISH_TRIGGERS):
        text_to_check = quick_reply_reason if quick_reply_option else user_message
        is_valid, reason = validate_user_message(text_to_check)
        if not is_valid:
            return JsonResponse({
                'response': reason,
                'is_invalid_input': True,
                'session_status': session.status,
                'timestamp': timezone.now().strftime('%H:%M'),
            })

    msg_type = 'quick_reply' if quick_reply_option else 'normal'

    # Entropy node actual
    phase_to_node = {
        'ambiguity': 'ambiguity',
        'pressure': 'time_pressure',
        'dilemma': 'ethical_dilemma',
        'completed': 'ethical_dilemma',
    }
    current_node = phase_to_node.get(session.current_phase, 'ambiguity')

    # Guardar mensaje del usuario con telemetría
    ChatMessage.objects.create(
        session=session, role='user', content=user_message,
        message_type=msg_type,
        quick_reply_option=quick_reply_option,
        response_time_seconds=response_time,
        total_pause_seconds=total_pause,
        latency_reading_ms=latency_reading,
        latency_execution_ms=latency_execution,
        backspace_count=backspace_count,
        entropy_node=current_node,
    )

    # Incrementar contador de interacciones
    session.n_interactions += 1

    # Llamar a la IA (ahora devuelve dict con clasificación)
    ai_result = get_ai_response(
        user_message, session, session.case,
        quick_reply_option=quick_reply_option,
        quick_reply_reason=quick_reply_reason,
    )

    ai_text = ai_result.get('respuesta_simulador', '')
    classification = ai_result.get('clasificacion_variable')
    justification = ai_result.get('justificacion_oculta', '')
    had_error = ai_result.get('had_error', False)

    if had_error:
        notify_admin_ia_error(request.user, session, 'Motor IA no disponible')
        error_msg = get_ia_error_message()
        ChatMessage.objects.create(
            session=session, role='system',
            content=error_msg, message_type='error_ia',
            entropy_node=current_node,
        )
        return JsonResponse({
            'response': error_msg,
            'is_error': True,
            'timestamp': timezone.now().strftime('%H:%M'),
            'session_status': session.status,
        })

    # Actualizar acumuladores según clasificación
    if classification == 'Ac':
        session.acumulado_ac += 1
    elif classification == 'Sm':
        session.acumulado_sm += 1
    elif classification == 'Ts':
        session.acumulado_ts += 1

    # Recalcular NChs
    n = session.n_interactions
    if n > 0:
        session.nchs_score = round(
            ((session.acumulado_ac + session.acumulado_sm) - session.acumulado_ts) / n, 3
        )

    # Guardar respuesta IA con clasificación
    ai_msg = ChatMessage.objects.create(
        session=session, role='assistant', content=ai_text,
        classification_variable=classification,
        ai_justification=justification,
        entropy_node=current_node,
    )

    # Cerrar sesión si el usuario quiso finalizar
    if any(t in user_message.lower() for t in FINISH_TRIGGERS):
        session.status = 'completado'
        session.completed_at = timezone.now()
        session.ia_feedback = ai_text

    # Avanzar de fase si corresponde
    phase_order = ['ambiguity', 'pressure', 'dilemma']
    if not any(t in user_message.lower() for t in FINISH_TRIGGERS):
        if session.current_phase in phase_order and _should_advance_phase(session):
            idx = phase_order.index(session.current_phase)
            if idx < len(phase_order) - 1:
                next_phase = phase_order[idx + 1]
                session.current_phase = next_phase
                phase_intro = {
                    'pressure': (
                        "---\n"
                        "**Fase 2 — Presión**\n\n"
                        "Bien, has identificado un punto ciego. Pero las cosas se complican: "
                        "acaba de surgir un agravante externo inesperado. "
                        "Tu margen de maniobra se redujo. ¿Qué acción táctica tomas ahora?"
                    ),
                    'dilemma': (
                        "---\n"
                        "**Fase 3 — El Dilema**\n\n"
                        "Has sorteado la presión. Ahora enfrentas el verdadero reto: "
                        "existe una solución altamente eficiente, pero implica un riesgo "
                        "ético, reputacional o de fricción cultural. "
                        "¿Hasta dónde estás dispuesto a llegar para resolver el caso?"
                    ),
                    'completed': (
                        "---\n"
                        "**Fases completadas**\n\n"
                        "Has atravesado ambigüedad, presión y un dilema ético. "
                        "Tu sesión será revisada por tu MAE. "
                        "Escribe **'evaluar'** si deseas recibir retroalimentación inmediata."
                    ),
                }
                intro_text = phase_intro.get(next_phase, '')
                if intro_text:
                    next_node = phase_to_node.get(next_phase, 'ambiguity')
                    ChatMessage.objects.create(
                        session=session, role='assistant',
                        content=intro_text, message_type='system_info',
                        entropy_node=next_node,
                    )
                    ai_text = ai_text + '\n\n' + intro_text
            else:
                session.current_phase = 'completed'

    session.save()

    return JsonResponse({
        'response': ai_text,
        'timestamp': ai_msg.created_at.strftime('%H:%M'),
        'session_status': session.status,
        'is_error': False,
        'current_phase': session.current_phase,
        'nchs_score': float(session.nchs_score),
    })


# ── Panel del MAE ─────────────────────────────────────────────────────────────

@login_required
def mae_review(request, session_id):
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(CaseSession, id=session_id)
    chat_messages = session.messages.all()

    if request.method == 'POST':
        verdict = request.POST.get('mae_verdict', '').strip()
        approved = request.POST.get('mae_approved') == 'true'

        session.mae = request.user
        session.mae_verdict = verdict
        session.mae_approved = approved
        session.status = 'evaluado'
        session.mae_reviewed_at = timezone.now()
        session.save()

        return redirect('dashboard')

    return render(request, 'cases/mae_review.html', {
        'session': session, 'chat_messages': chat_messages, 'case': session.case,
    })


@login_required
def mae_diagnosis_review(request, session_id):
    """El MAE revisa el diagnóstico (5 preguntas) y aprueba o rechaza al gerente."""
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(DiagnosisSession, id=session_id)
    chat_messages = session.messages.all()

    if request.method == 'POST':
        verdict = request.POST.get('mae_verdict', '').strip()
        approved = request.POST.get('mae_approved') == 'true'

        session.mae = request.user
        session.mae_verdict = verdict
        session.mae_approved = approved
        session.status = 'aprobado' if approved else 'rechazado'
        session.mae_reviewed_at = timezone.now()
        session.save()

        return redirect('dashboard')

    return render(request, 'cases/mae_diagnosis_review.html', {
        'session': session, 'chat_messages': chat_messages,
    })


# ── Pre-evaluación ─────────────────────────────────────────────────────────────

@login_required
def pre_evaluation(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)

    # Si ya tiene pre-evaluación, redirigir al chat
    if hasattr(session, 'pre_evaluation'):
        return redirect('chat', session_id=session.id)

    if request.method == 'POST':
        control = int(request.POST.get('perceived_control_score', 3))
        trust = int(request.POST.get('ia_trust_baseline', 3))
        ego = request.POST.get('initial_ego_statement', '').strip()

        from .models import PreEvaluation
        PreEvaluation.objects.create(
            session=session,
            user=request.user,
            perceived_control_score=control,
            ia_trust_baseline=trust,
            initial_ego_statement=ego,
        )
        return redirect('chat', session_id=session.id)

    return render(request, 'cases/pre_evaluation.html', {
        'session': session, 'case': session.case,
    })


# ── Post-autopsia ──────────────────────────────────────────────────────────────

@login_required
def post_autopsy(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)

    # Solo sesiones completadas pueden tener autopsia
    if session.status not in ('completado', 'en_revision', 'evaluado', 'abandoned'):
        return redirect('chat', session_id=session.id)

    # Si ya tiene post-autopsia, redirigir al dashboard
    if hasattr(session, 'post_autopsy'):
        return redirect('dashboard')

    if request.method == 'POST':
        shock = request.POST.get('shock_reflection', '').strip()
        negotiation = request.POST.get('negotiation_strategy', '').strip()
        law_sov = request.POST.get('law_sovereignty', '').strip()
        law_id = request.POST.get('law_identity', '').strip()

        from .models import PostAutopsy
        PostAutopsy.objects.create(
            session=session,
            user=request.user,
            shock_reflection=shock,
            negotiation_strategy=negotiation,
            law_sovereignty=law_sov,
            law_identity=law_id,
        )
        return redirect('dashboard')

    return render(request, 'cases/post_autopsy.html', {
        'session': session, 'case': session.case,
    })


# ── Heartbeat ───────────────────────────────────────────────────────────────────

@login_required
@require_POST
def heartbeat(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)
    session.last_heartbeat = timezone.now()
    session.save(update_fields=['last_heartbeat'])
    return JsonResponse({'ok': True})


# ── Exportación ─────────────────────────────────────────────────────────────────

@login_required
def export_session_json(request, session_id):
    if not request.user.is_mae and not request.user.is_admin_role:
        return redirect('dashboard')
    session = get_object_or_404(CaseSession, id=session_id)
    messages = session.messages.all()

    # Perfil del gerente
    profile = {}
    try:
        mp = session.user.manager_profile
        profile = {
            'cargo': mp.position,
            'empresa': mp.company,
            'industria': mp.get_industry_display(),
            'experiencia_anos': mp.get_experience_years_display(),
            'nivel': mp.get_level_display(),
        }
    except Exception:
        pass

    # Pre-evaluación
    pre_eval = None
    try:
        pe = session.pre_evaluation
        pre_eval = {
            'control_percibido': pe.perceived_control_score,
            'confianza_ia_inicial': pe.ia_trust_baseline,
            'declaracion_ego': pe.initial_ego_statement,
        }
    except Exception:
        pass

    # Post-autopsia
    post_autopsy = None
    try:
        pa = session.post_autopsy
        post_autopsy = {
            'reflexion_choque': pa.shock_reflection,
            'estrategia_negociacion': pa.negotiation_strategy,
            'ley_soberan_1': pa.law_sovereignty,
            'ley_identidad': pa.law_identity,
        }
    except Exception:
        pass

    # Transcripción del diálogo
    corpus = []
    for msg in messages:
        if msg.message_type != 'system_info':
            entry = {
                'nodo_entropia': msg.entropy_node,
                'rol': msg.role,
                'texto': msg.content,
            }
            if msg.role == 'assistant' and msg.classification_variable:
                entry['evaluacion_sistema'] = {
                    'variable_asignada': msg.classification_variable,
                    'justificacion_ia': msg.ai_justification,
                }
            corpus.append(entry)

    # Tutor asignado
    tutor = None
    if session.teacher:
        tutor = session.teacher.user.get_full_name()

    export = {
        'investigacion_codigo': 'MAE-DOCTORADO-2026',
        'meta_sesion': {
            'session_id': session.id,
            'fecha': session.started_at.strftime('%Y-%m-%d'),
            'estado_final': session.status,
            'tutor_asignado': tutor,
            'nchs_final': float(session.nchs_score),
            'n_interacciones': session.n_interactions,
            'acumulado_ac': session.acumulado_ac,
            'acumulado_sm': session.acumulado_sm,
            'acumulado_ts': session.acumulado_ts,
        },
        'sujeto_biologico': {
            'user_id': session.user.id,
            'nombre': session.user.get_full_name(),
            **profile,
        },
        'linea_base_subjetiva': pre_eval,
        'corpus_transcripcion_dialogo': corpus,
        'clausura_fenomenologica': post_autopsy,
    }

    response = JsonResponse(export, json_dumps_params={'indent': 2, 'ensure_ascii': False})
    response['Content-Disposition'] = f'attachment; filename="mae_sesion_{session.id}.json"'
    return response


@login_required
def export_csv(request):
    if not request.user.is_mae and not request.user.is_admin_role:
        return redirect('dashboard')
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mae_telemetria.csv"'
    response.write('\ufeff')  # BOM para Excel

    writer = csv.writer(response)
    writer.writerow([
        'Session_ID', 'User_ID', 'Nombre', 'Nivel', 'Experiencia',
        'Entropy_Node', 'Interaction_Number', 'Role',
        'Classification_Variable', 'AI_Justification',
        'Latency_Reading_MS', 'Latency_Execution_MS', 'Backspace_Count',
        'Current_NCHs_Score', 'Created_At',
    ])

    sessions = CaseSession.objects.select_related('user', 'case').prefetch_related('messages').all()
    interaction_counter = {}

    for session in sessions:
        key = session.id
        interaction_counter[key] = 0
        profile_level = 'sin_nivel'
        profile_exp = ''
        try:
            mp = session.user.manager_profile
            profile_level = mp.get_level_display()
            profile_exp = mp.get_experience_years_display()
        except Exception:
            pass

        for msg in session.messages.all():
            if msg.role == 'user':
                interaction_counter[key] += 1
            writer.writerow([
                session.id,
                session.user.id,
                session.user.get_full_name(),
                profile_level,
                profile_exp,
                msg.entropy_node,
                interaction_counter[key],
                msg.role,
                msg.classification_variable or '',
                msg.ai_justification or '',
                msg.latency_reading_ms or '',
                msg.latency_execution_ms or '',
                msg.backspace_count or '',
                float(session.nchs_score),
                msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            ])

    return response
