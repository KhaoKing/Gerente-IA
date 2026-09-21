import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage, IAErrorLog, AIConfiguration, CaseAudit
from .ai_engine import (
    get_ai_response, get_diagnosis_response, get_ia_error_message,
    notify_admin_ia_error, DIAGNOSIS_QUESTIONS, is_finish_trigger,
    validate_user_message, _should_advance_phase, PHASE_LABELS,
    test_connection,
)

logger = logging.getLogger(__name__)


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
            user=user, status__in=['completado', 'en_validacion', 'observado', 'corregido', 'cerrado']
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
        from django.db.models import Avg, Count, Max, Min, Q
        from django.db.models.functions import TruncDate
        from datetime import timedelta

        # ── Filtros del dashboard ──
        status_filter = request.GET.get('status', '')
        gerente_filter = request.GET.get('gerente', '')
        category_filter = request.GET.get('category', '')
        priority_filter = request.GET.get('priority', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')

        # Piezas de filtro por dimensión — se combinan distinto según la query:
        # algunas ya fijan su propio status/priority, así que ahí se omite esa pieza
        # para no auto-anularse con lo que el usuario eligió en el formulario.
        status_q = Q(status=status_filter) if status_filter else Q()
        gerente_q = Q(user_id=gerente_filter) if gerente_filter else Q()
        category_q = Q(case__category=category_filter) if category_filter else Q()
        priority_q = Q(priority=priority_filter) if priority_filter else Q()
        date_from_q = Q(started_at__date__gte=date_from) if date_from else Q()
        date_to_q = Q(started_at__date__lte=date_to) if date_to else Q()

        # Filtro completo (para CaseSession sin status/priority propios ya fijados)
        session_filter = status_q & gerente_q & category_q & priority_q & date_from_q & date_to_q
        # Sin status (para listas que ya fijan su propio status, ej. pendientes/abandonadas/escaladas)
        scope_filter = gerente_q & category_q & priority_q & date_from_q & date_to_q
        # Sin status ni priority (para KPIs de SLA/críticos que ya fijan priority='alta')
        kpi_filter = gerente_q & category_q & date_from_q & date_to_q

        # Misma idea pero para queries sobre ChatMessage (los campos van con prefijo session__)
        msg_filter = Q()
        if status_filter:
            msg_filter &= Q(session__status=status_filter)
        if gerente_filter:
            msg_filter &= Q(session__user_id=gerente_filter)
        if category_filter:
            msg_filter &= Q(session__case__category=category_filter)
        if priority_filter:
            msg_filter &= Q(session__priority=priority_filter)
        if date_from:
            msg_filter &= Q(session__started_at__date__gte=date_from)
        if date_to:
            msg_filter &= Q(session__started_at__date__lte=date_to)

        diagnosis_filter = Q()
        if gerente_filter:
            diagnosis_filter &= Q(user_id=gerente_filter)
        if date_from:
            diagnosis_filter &= Q(completed_at__date__gte=date_from)
        if date_to:
            diagnosis_filter &= Q(completed_at__date__lte=date_to)

        # Diagnósticos completados esperando validación del Docente Tutor
        pending_diagnoses = DiagnosisSession.objects.filter(
            status='completado'
        ).filter(diagnosis_filter).select_related('user').order_by('-completed_at')

        # Sesiones de caso pendientes de revisión
        pending_reviews = CaseSession.objects.filter(
            status='completado'
        ).filter(scope_filter).select_related('user', 'case').order_by('-completed_at')

        in_review = CaseSession.objects.filter(
            mae=user, status='en_validacion'
        ).filter(scope_filter).select_related('user', 'case')
        all_manager_sessions = CaseSession.objects.filter(session_filter).select_related('user', 'case').order_by('-started_at')

        managers_list = UserModel.objects.filter(role='gerente').prefetch_related('manager_profile')

        # ── Métricas agregadas por gerente (directorio) ──
        manager_sessions = CaseSession.objects.filter(session_filter).select_related('user')
        manager_data = {}
        for s in manager_sessions:
            uid = s.user_id
            if uid not in manager_data:
                manager_data[uid] = {
                    'total': 0, 'active': 0, 'pending': 0,
                    'overdue': 0, 'nchs_list': [],
                }
            d = manager_data[uid]
            d['total'] += 1
            if s.status in ('en_progreso',):
                d['active'] += 1
            if s.status in ('completado',):
                d['pending'] += 1
            if s.is_overdue() or s.sla_breached:
                d['overdue'] += 1
            if s.nchs_score is not None:
                d['nchs_list'].append(float(s.nchs_score))

        managers_enriched = []
        for m in managers_list:
            d = manager_data.get(m.id, {'total':0, 'active':0, 'pending':0, 'overdue':0, 'nchs_list':[]})
            nchs_scores = d['nchs_list']
            avg_nchs = round(sum(nchs_scores) / len(nchs_scores), 3) if nchs_scores else 0
            last = nchs_scores[-1] if len(nchs_scores) >= 1 else None
            prev = nchs_scores[-2] if len(nchs_scores) >= 2 else None
            trend = None
            if last is not None and prev is not None:
                trend = round(last - prev, 3)
            managers_enriched.append({
                'id': m.id,
                'name': m.get_full_name(),
                'total': d['total'],
                'active': d['active'],
                'pending': d['pending'],
                'overdue': d['overdue'],
                'avg_nchs': avg_nchs,
                'trend': trend,
            })

        # ── Métricas de tiempos de respuesta ──
        response_metrics = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).filter(msg_filter).aggregate(
            avg_response=Avg('response_time_seconds'),
            max_response=Max('response_time_seconds'),
            avg_pause=Avg('total_pause_seconds'),
        )

        # Métricas finas de telemetría (ms)
        fine_metrics = ChatMessage.objects.filter(
            role='user', latency_reading_ms__isnull=False
        ).filter(msg_filter).aggregate(
            avg_reading=Avg('latency_reading_ms'),
            avg_execution=Avg('latency_execution_ms'),
            avg_backspaces=Avg('backspace_count'),
        )

        # Top gerentes por tiempo de respuesta promedio
        user_metrics_raw = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).filter(msg_filter).values(
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
        ).filter(session_filter).select_related('user').order_by('-nchs_score')

        nchs_aggregate = CaseSession.objects.filter(
            n_interactions__gt=0
        ).filter(session_filter).aggregate(
            avg_nchs=Avg('nchs_score'),
            max_nchs=Max('nchs_score'),
            min_nchs=Min('nchs_score'),
        )

        # Clasificaciones por tipo
        classification_counts = ChatMessage.objects.filter(
            classification_variable__isnull=False
        ).filter(msg_filter).values('classification_variable').annotate(count=Count('id'))
        class_data = {c['classification_variable']: c['count'] for c in classification_counts}

        # Sesiones abandonadas
        abandoned_sessions = CaseSession.objects.filter(
            status='abandoned'
        ).filter(scope_filter).select_related('user').order_by('-last_heartbeat')

        # Sesiones con SLA vencido
        from django.utils import timezone
        overdue_sessions = CaseSession.objects.filter(
            sla_deadline__isnull=False,
            sla_breached=False,
            sla_deadline__lt=timezone.now()
        ).filter(scope_filter).select_related('user', 'case').order_by('sla_deadline')

        # Sesiones escaladas
        escalated_sessions = CaseSession.objects.filter(
            status='escalado'
        ).filter(scope_filter).select_related('user', 'case').order_by('-started_at')

        # ── KPI: críticos (alta prioridad + SLA vencido) ──
        critical_sessions = CaseSession.objects.filter(
            priority='alta',
            sla_deadline__isnull=False,
            sla_breached=True,
        ).filter(kpi_filter).count()

        # ── % Cumplimiento SLA ──
        total_with_sla = CaseSession.objects.filter(sla_deadline__isnull=False).filter(kpi_filter).count()
        breached_count = CaseSession.objects.filter(sla_breached=True).filter(kpi_filter).count()
        sla_compliance = round((total_with_sla - breached_count) / max(total_with_sla, 1) * 100, 1)

        # ── Serie temporal: últimos 7 días ──
        seven_days_ago = timezone.now().date() - timedelta(days=6)
        daily_metrics_raw = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False,
            created_at__date__gte=seven_days_ago
        ).filter(msg_filter).annotate(
            day=TruncDate('created_at')
        ).values('day').annotate(
            avg_response=Avg('response_time_seconds'),
            msg_count=Count('id')
        ).order_by('day')

        daily_metrics = []
        for d in daily_metrics_raw:
            daily_metrics.append({
                'day': d['day'].strftime('%d/%m'),
                'avg_response': round(d['avg_response'], 1),
                'count': d['msg_count'],
            })

        # ── Segmentación por categoría ──
        category_metrics_raw = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).filter(msg_filter).values(
            'session__case__category'
        ).annotate(
            avg_response=Avg('response_time_seconds'),
            msg_count=Count('id')
        ).order_by('avg_response')

        category_metrics = []
        category_labels = dict(ManagementCase.CATEGORY_CHOICES)
        for c in category_metrics_raw:
            cat = c['session__case__category']
            category_metrics.append({
                'label': category_labels.get(cat, cat),
                'avg_response': round(c['avg_response'], 1),
                'count': c['msg_count'],
            })

        # ── Query string de filtros para links persistentes ──
        filter_params = []
        for key in ['status', 'gerente', 'category', 'priority', 'date_from', 'date_to']:
            val = request.GET.get(key, '')
            if val:
                filter_params.append(f'{key}={val}')
        filter_qs = '&'.join(filter_params)

        total_measured = ChatMessage.objects.filter(
            role='user', response_time_seconds__isnull=False
        ).filter(msg_filter).count()

        context.update({
            'pending_diagnoses': pending_diagnoses,
            'pending_reviews': pending_reviews,
            'in_review': in_review,
            'all_sessions': all_manager_sessions,
            'managers_list': managers_list,
            'managers_enriched': managers_enriched,
            'response_metrics': response_metrics,
            'fine_metrics': fine_metrics,
            'user_metrics': user_metrics,
            'total_measured_messages': total_measured,
            'nchs_sessions': nchs_sessions,
            'nchs_aggregate': nchs_aggregate,
            'class_data': class_data,
            'abandoned_sessions': abandoned_sessions,
            'overdue_sessions': overdue_sessions,
            'escalated_sessions': escalated_sessions,
            'critical_count': critical_sessions,
            'sla_compliance': sla_compliance,
            'total_with_sla': total_with_sla,
            'daily_metrics': daily_metrics,
            'category_metrics': category_metrics,
            'filter_qs': filter_qs,
            # Filtros activos
            'filter_status': status_filter,
            'filter_gerente': gerente_filter,
            'filter_category': category_filter,
            'filter_priority': priority_filter,
            'filter_date_from': date_from,
            'filter_date_to': date_to,
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
    # Solo superusuario (no cualquier rol 'admin'): la configuración de IA y el
    # consumo de tokens quedan ocultos incluso para una cuenta admin de demostración.
    if not request.user.is_superuser:
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


@login_required
@require_POST
def test_ai_connection(request):
    """Chatbox de prueba: valida la conectividad con el proveedor de IA activo."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    data = json.loads(request.body)
    message = data.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Escribe un mensaje de prueba.'}, status=400)

    result = test_connection(message)
    return JsonResponse(result)


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
            # El Docente Tutor rechazó: reiniciamos el diagnóstico reusando la misma sesión
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
                    "Vamos a repetir el diagnóstico según indicó tu Docente Tutor.\n\n"
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
            # Esperando Docente Tutor
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
            "¡Hola! Soy tu MAE.\n\n"
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

        # Marcar perfil como diagnóstico completado (nivel se asigna cuando el Docente Tutor lo revise)
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
    # aprobado por el Docente Tutor. Antes de eso, su único botón disponible es el del
    # diagnóstico inicial (5 preguntas).
    if request.user.is_gerente:
        try:
            d_session = request.user.diagnosis_session
        except DiagnosisSession.DoesNotExist:
            return redirect('start_diagnosis')
        if not (d_session.mae_approved is True or d_session.status in ('aprobado', 'nivel_asignado')):
            return redirect('dashboard')

    completed_ids = CaseSession.objects.filter(
        user=request.user, status__in=['completado', 'en_validacion', 'observado', 'corregido', 'cerrado']
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

    session = CaseSession.objects.create(
        user=request.user, case=case, current_phase='ambiguity',
        status='en_progreso', priority=case.priority,
        sla_deadline=timezone.now() + timezone.timedelta(hours=case.sla_hours) if case.sla_hours else None,
    )
    CaseAudit.objects.create(
        session=session, user=request.user, action='created',
        previous_status='', new_status='en_progreso',
    )
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
    if session.status in ('completado', 'en_validacion', 'observado', 'corregido', 'cerrado') and not hasattr(session, 'post_autopsy'):
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
    if not is_finish_trigger(user_message):
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
    if is_finish_trigger(user_message):
        session.completed_at = timezone.now()
        session.ia_feedback = ai_text
        if not session.sla_deadline and session.case.sla_hours:
            session.sla_deadline = timezone.now() + timezone.timedelta(hours=session.case.sla_hours)

        new_hash = session.compute_content_hash()
        if CaseSession.objects.filter(content_hash=new_hash).exclude(id=session.id).exists():
            logger.warning(f"Sesión {session.id}: contenido idéntico a otra sesión existente (hash={new_hash}).")
        else:
            session.content_hash = new_hash

        session.transition_to('completado', user=request.user)

    # Avanzar de fase si corresponde
    phase_order = ['ambiguity', 'pressure', 'dilemma']
    if not is_finish_trigger(user_message):
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
                        "Tu sesión será revisada por tu Docente Tutor. "
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


# ── Panel del Docente Tutor ─────────────────────────────────────────────────────────────

@login_required
def mae_review(request, session_id):
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(CaseSession, id=session_id)
    chat_messages = session.messages.all()

    if request.method == 'POST':
        verdict = request.POST.get('mae_verdict', '').strip()
        approved = request.POST.get('mae_approved') == 'true'
        new_status = request.POST.get('new_status', '')

        session.mae = request.user
        session.mae_verdict = verdict
        session.mae_approved = approved
        session.mae_reviewed_at = timezone.now()

        if new_status and new_status in dict(CaseSession.STATUS_CHOICES):
            session.transition_to(new_status, user=request.user, observation=verdict)
        elif approved:
            session.transition_to('cerrado', user=request.user, observation=verdict, action='approved')
        else:
            session.transition_to('observado', user=request.user, observation=verdict, action='rejected')

        session.save()

        return redirect('dashboard')

    if session.status == 'completado' and session.can_transition_to('en_validacion'):
        session.transition_to('en_validacion', user=request.user)

    return render(request, 'cases/mae_review.html', {
        'session': session, 'chat_messages': chat_messages, 'case': session.case,
    })


@login_required
def mae_diagnosis_review(request, session_id):
    """El Docente Tutor revisa el diagnóstico (5 preguntas) y aprueba o rechaza al gerente."""
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


@login_required
def diagnosis_detail(request, session_id):
    if not (request.user.is_mae or request.user.is_admin_role):
        return redirect('dashboard')

    session = get_object_or_404(DiagnosisSession.objects.select_related('user'), id=session_id)
    messages = session.messages.all()

    try:
        profile = session.user.manager_profile
    except Exception:
        profile = None

    return render(request, 'cases/diagnosis_detail.html', {
        'session': session,
        'messages': messages,
        'profile': profile,
    })


# ── Escalamiento ────────────────────────────────────────────────────────────────

@login_required
def mae_escalate(request, session_id):
    if not request.user.is_mae:
        return redirect('dashboard')

    session = get_object_or_404(CaseSession, id=session_id)

    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        target_mae_id = request.POST.get('target_mae', '')

        session.transition_to('escalado', user=request.user, observation=motivo, action='escalated')

        if target_mae_id:
            from accounts.models import User as UserModel
            try:
                new_mae = UserModel.objects.get(id=target_mae_id, role='mae')
                previous_mae = session.mae.get_full_name() if session.mae else 'Sin asignar'
                session.mae = new_mae
                session.save(update_fields=['mae'])
                CaseAudit.objects.create(
                    session=session, user=request.user,
                    action='escalated',
                    previous_status='', new_status='',
                    observation=f'Reasignado: {previous_mae} → {new_mae.get_full_name()} — {motivo}',
                )
            except UserModel.DoesNotExist:
                pass

        return redirect('dashboard')

    from accounts.models import User as UserModel
    mae_list = UserModel.objects.filter(role='mae').exclude(id=request.user.id)

    return render(request, 'cases/mae_escalate.html', {
        'session': session, 'case': session.case, 'mae_list': mae_list,
    })


# ── Detalle de caso (Expediente) ────────────────────────────────────────────────

@login_required
def case_detail(request, session_id):
    """Vista detallada del expediente de un caso para el Docente Tutor."""
    if not (request.user.is_mae or request.user.is_admin_role):
        return redirect('dashboard')

    session = get_object_or_404(CaseSession.objects.select_related('user', 'case'), id=session_id)
    chat_messages = session.messages.all()
    audit_logs = session.audit_logs.select_related('user').order_by('-created_at')

    try:
        pre_eval = session.pre_evaluation
    except Exception:
        pre_eval = None
    try:
        post_autopsy = session.post_autopsy
    except Exception:
        post_autopsy = None
    try:
        profile = session.user.manager_profile
    except Exception:
        profile = None

    return render(request, 'cases/case_detail.html', {
        'session': session,
        'case': session.case,
        'chat_messages': chat_messages,
        'audit_logs': audit_logs,
        'pre_eval': pre_eval,
        'post_autopsy': post_autopsy,
        'profile': profile,
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
    if session.status not in ('completado', 'en_validacion', 'observado', 'corregido', 'cerrado', 'abandoned'):
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
def export_pdf(request):
    if not request.user.is_mae and not request.user.is_admin_role:
        return redirect('dashboard')

    import io
    from django.db.models import Avg, Q
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    # Aplicar los mismos filtros del dashboard
    status_filter = request.GET.get('status', '')
    gerente_filter = request.GET.get('gerente', '')
    category_filter = request.GET.get('category', '')
    priority_filter = request.GET.get('priority', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    session_filter = Q()
    if status_filter:
        session_filter &= Q(status=status_filter)
    if gerente_filter:
        session_filter &= Q(user_id=gerente_filter)
    if category_filter:
        session_filter &= Q(case__category=category_filter)
    if priority_filter:
        session_filter &= Q(priority=priority_filter)
    if date_from:
        session_filter &= Q(started_at__date__gte=date_from)
    if date_to:
        session_filter &= Q(started_at__date__lte=date_to)

    sessions = CaseSession.objects.filter(session_filter).select_related('user', 'case').annotate(
        avg_response=Avg('messages__response_time_seconds'),
        avg_pause=Avg('messages__total_pause_seconds'),
    ).order_by('-started_at')

    header = ['Hash', 'Gerente', 'Prom. Respuestas (s)', 'Prom. Pausas (s)', 'AC', 'SM', 'TS', 'Caso']
    rows = [header]

    total_ac = total_sm = total_ts = 0

    for s in sessions:
        avg_r = s.avg_response
        avg_p = s.avg_pause
        total_ac += s.acumulado_ac
        total_sm += s.acumulado_sm
        total_ts += s.acumulado_ts

        rows.append([
            (s.content_hash[:12] + '\u2026') if s.content_hash else '\u2014',
            s.user.get_full_name(),
            f"{avg_r:.1f}" if avg_r is not None else '\u2014',
            f"{avg_p:.1f}" if avg_p is not None else '\u2014',
            str(s.acumulado_ac),
            str(s.acumulado_sm),
            str(s.acumulado_ts),
            s.case.title,
        ])

    # Promedio general ponderado sobre TODOS los mensajes (no el promedio de los
    # promedios por sesi\u00f3n, que sesga si las sesiones tienen distinta cantidad de mensajes).
    grand_metrics = ChatMessage.objects.filter(session__in=sessions).aggregate(
        avg_response=Avg('response_time_seconds'),
        avg_pause=Avg('total_pause_seconds'),
    )

    total_row = [
        'TOTAL',
        f'{sessions.count()} sesi\u00f3n(es)',
        f"{grand_metrics['avg_response']:.1f}" if grand_metrics['avg_response'] is not None else '\u2014',
        f"{grand_metrics['avg_pause']:.1f}" if grand_metrics['avg_pause'] is not None else '\u2014',
        str(total_ac),
        str(total_sm),
        str(total_ts),
        '',
    ]
    rows.append(total_row)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    elements = [
        Paragraph('Reporte de Sesiones \u2014 Gerente IA', styles['Title']),
        Paragraph(
            f"Generado: {timezone.now().strftime('%d/%m/%Y %H:%M')} \u00b7 "
            f"{sessions.count()} sesi\u00f3n(es)",
            styles['Normal'],
        ),
        Spacer(1, 0.6 * cm),
    ]

    table = Table(rows, repeatRows=1, colWidths=[3.2*cm, 4.5*cm, 3.3*cm, 3.0*cm, 1.6*cm, 1.6*cm, 1.6*cm, 6*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (6, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.4 * cm))
    elements.append(Paragraph(
        "<b>TOTAL</b> — Prom. Respuestas / Pausas: promedio general ponderado sobre todos los "
        "mensajes (no el promedio de los promedios por fila). AC / SM / TS: suma total.",
        styles['Normal'],
    ))
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename_parts = ['mae_reporte']
    if gerente_filter:
        filename_parts.append(f'gerente_{gerente_filter}')
    if status_filter:
        filename_parts.append(status_filter)
    response['Content-Disposition'] = f'attachment; filename="{"_".join(filename_parts)}.pdf"'
    return response
