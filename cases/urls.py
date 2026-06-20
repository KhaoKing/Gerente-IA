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
    # API config
    path('api/configuracion/', views.api_config, name='api_config'),
    # MAE
    path('mae/revision/<int:session_id>/', views.mae_review, name='mae_review'),
    path('mae/diagnostico/<int:session_id>/', views.mae_diagnosis_review, name='mae_diagnosis_review'),
    # Heartbeat y exportación
    path('caso/<int:session_id>/heartbeat/', views.heartbeat, name='heartbeat'),
    path('mae/exportar/<int:session_id>/json/', views.export_session_json, name='export_json'),
    path('mae/exportar/csv/', views.export_csv, name='export_csv'),
    # Pre/Post evaluación
    path('caso/<int:session_id>/pre-evaluacion/', views.pre_evaluation, name='pre_evaluation'),
    path('caso/<int:session_id>/post-autopsia/', views.post_autopsy, name='post_autopsy'),
]
