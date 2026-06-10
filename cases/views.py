import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage, IAErrorLog
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
        # Diagnósticos completados esperando validación del MAE
        pending_diagnoses = DiagnosisSession.objects.filter(
            status='completado'
        ).select_related('user').order_by('-completed_at')

        # Sesiones de caso pendientes de revisión — la cola de trabajo del MAE
        pending_reviews = CaseSession.objects.filter(
            status='completado'
        ).select_related('user', 'case').order_by('-completed_at')

        in_review = CaseSession.objects.filter(
            mae=user, status='en_revision'
        ).select_related('user', 'case')
        all_manager_sessions = CaseSession.objects.select_related('user', 'case').order_by('-started_at')

        managers_list = UserModel.objects.filter(role='gerente').prefetch_related('manager_profile')

        context.update({
            'pending_diagnoses': pending_diagnoses,
            'pending_reviews': pending_reviews,
            'in_review': in_review,
            'all_sessions': all_manager_sessions,
            'managers_list': managers_list,
        })

    elif user.is_admin_role:
        from accounts.models import User as UserModel
        ia_errors = IAErrorLog.objects.order_by('-created_at')[:10]
        context.update({
            'total_users': UserModel.objects.count(),
            'total_managers': UserModel.objects.filter(role='gerente').count(),
            'total_maes': UserModel.objects.filter(role='mae').count(),
            'total_cases': ManagementCase.objects.count(),
            'active_sessions': CaseSession.objects.filter(status='en_progreso').count(),
            'pending_reviews': CaseSession.objects.filter(status='completado').count(),
            'ia_errors': ia_errors,
        })

    return render(request, 'cases/dashboard.html', context)


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
    messages = session.messages.all()
    return render(request, 'cases/diagnosis_chat.html', {'session': session, 'messages': messages})


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
    return redirect('chat', session_id=session.id)


@login_required
def chat_view(request, session_id):
    session = get_object_or_404(CaseSession, id=session_id, user=request.user)
    messages = session.messages.all()
    last_ai_msg = messages.filter(role='assistant').last()
    phase_label = dict(CaseSession.PHASE_CHOICES).get(session.current_phase, '')
    context = {
        'session': session, 'messages': messages, 'case': session.case,
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
    quick_reply_option = data.get('quick_reply_option', '')   # 'agree'|'disagree'|'incomplete'
    quick_reply_reason = data.get('quick_reply_reason', '').strip()
    response_time = data.get('response_time_seconds')
    total_pause = data.get('total_pause_seconds')

    if not user_message:
        return JsonResponse({'error': 'Mensaje vacío.'}, status=400)

    # Validar coherencia del mensaje del usuario (rechazar gibberish tipo "cnasooq1").
    # Las palabras de cierre ('evaluar', 'listo', etc.) siempre se permiten.
    msg_lower = user_message.lower()
    if not any(t in msg_lower for t in FINISH_TRIGGERS):
        # Si es quick reply, validamos la razón aportada (el textarea); si no, el mensaje libre
        text_to_check = quick_reply_reason if quick_reply_option else user_message
        is_valid, reason = validate_user_message(text_to_check)
        if not is_valid:
            return JsonResponse({
                'response': reason,
                'is_invalid_input': True,
                'session_status': session.status,
                'timestamp': timezone.now().strftime('%H:%M'),
            })

    # Determinar tipo de mensaje
    msg_type = 'quick_reply' if quick_reply_option else 'normal'

    # Guardar mensaje del usuario — SIEMPRE se guarda en BD
    ChatMessage.objects.create(
        session=session, role='user', content=user_message,
        message_type=msg_type,
        quick_reply_option=quick_reply_option,
        response_time_seconds=response_time,
        total_pause_seconds=total_pause,
    )

    # Llamar a la IA
    ai_text, had_error = get_ai_response(
        user_message, session, session.case,
        quick_reply_option=quick_reply_option,
        quick_reply_reason=quick_reply_reason,
    )

    if had_error:
        # Registrar error y notificar admin
        notify_admin_ia_error(request.user, session, 'Motor IA no disponible')
        error_msg = get_ia_error_message()
        ChatMessage.objects.create(
            session=session, role='system',
            content=error_msg, message_type='error_ia',
        )
        return JsonResponse({
            'response': error_msg,
            'is_error': True,
            'timestamp': timezone.now().strftime('%H:%M'),
            'session_status': session.status,
        })

    # Guardar respuesta IA
    ai_msg = ChatMessage.objects.create(
        session=session, role='assistant', content=ai_text,
    )

    # Cerrar sesión si el usuario quiso finalizar
    if any(t in user_message.lower() for t in FINISH_TRIGGERS):
        session.status = 'completado'
        session.completed_at = timezone.now()
        session.ia_feedback = ai_text
        session.save()

    # Avanzar de fase si corresponde
    phase_order = ['ambiguity', 'pressure', 'dilemma']
    if not any(t in user_message.lower() for t in FINISH_TRIGGERS):
        if session.current_phase in phase_order and _should_advance_phase(session):
            idx = phase_order.index(session.current_phase)
            if idx < len(phase_order) - 1:
                next_phase = phase_order[idx + 1]
                session.current_phase = next_phase
                session.save()
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
                    ChatMessage.objects.create(
                        session=session, role='assistant',
                        content=intro_text, message_type='system_info',
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
    })


# ── Panel del MAE ─────────────────────────────────────────────────────────────

@login_required
def mae_review(request, session_id):
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(CaseSession, id=session_id)
    messages = session.messages.all()

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
        'session': session, 'messages': messages, 'case': session.case,
    })


@login_required
def mae_diagnosis_review(request, session_id):
    """El MAE revisa el diagnóstico (5 preguntas) y aprueba o rechaza al gerente."""
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(DiagnosisSession, id=session_id)
    messages = session.messages.all()

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
        'session': session, 'messages': messages,
    })
