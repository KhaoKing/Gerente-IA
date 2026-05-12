from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    # Diagnóstico
    path('diagnostico/iniciar/', views.start_diagnosis, name='start_diagnosis'),
    path('diagnostico/chat/', views.diagnosis_chat, name='diagnosis_chat'),
    path('diagnostico/mensaje/', views.diagnosis_send, name='diagnosis_send'),
    # Casos
    path('caso/iniciar/', views.start_case, name='start_case'),
    path('caso/<int:session_id>/chat/', views.chat_view, name='chat'),
    path('caso/<int:session_id>/mensaje/', views.send_message, name='send_message'),
    # Coach
    path('coach/revision/<int:session_id>/', views.coach_review, name='coach_review'),
    path('coach/diagnostico/<int:session_id>/', views.coach_diagnosis_review, name='coach_diagnosis_review'),
]
