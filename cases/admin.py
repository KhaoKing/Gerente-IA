from django.contrib import admin
from .models import ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage, IAErrorLog


@admin.register(ManagementCase)
class ManagementCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'difficulty', 'is_active')
    list_filter = ('category', 'difficulty', 'is_active')
    search_fields = ('title',)


@admin.register(CaseSession)
class CaseSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'case', 'status', 'coach_approved', 'started_at')
    list_filter = ('status', 'coach_approved')
    readonly_fields = ('started_at',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'message_type', 'created_at')
    list_filter = ('role', 'message_type')


@admin.register(DiagnosisSession)
class DiagnosisSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'current_question', 'coach_approved', 'coach', 'started_at')
    list_filter = ('status', 'coach_approved')


@admin.register(DiagnosisMessage)
class DiagnosisMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'question_number', 'created_at')


@admin.register(IAErrorLog)
class IAErrorLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'error_type', 'notified_admin', 'created_at')
    list_filter = ('error_type', 'notified_admin')
    readonly_fields = ('created_at',)
