from django.contrib import admin
from .models import (
    ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage,
    TeacherProfile, PreEvaluation, PostAutopsy, AIConfiguration, IAErrorLog, CaseAudit,
)


@admin.register(ManagementCase)
class ManagementCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'difficulty', 'priority', 'sla_hours', 'is_active')
    list_filter = ('category', 'difficulty', 'priority', 'is_active')
    search_fields = ('title', 'description')


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    can_delete = False
    fields = (
        'created_at', 'role', 'message_type', 'content', 'quick_reply_option',
        'classification_variable', 'ai_justification', 'entropy_node',
    )
    readonly_fields = fields
    ordering = ('created_at',)

    def has_add_permission(self, request, obj=None):
        return False


class CaseAuditInline(admin.TabularInline):
    model = CaseAudit
    extra = 0
    can_delete = False
    fields = ('created_at', 'user', 'action', 'previous_status', 'new_status', 'observation')
    readonly_fields = fields
    ordering = ('created_at',)

    def has_add_permission(self, request, obj=None):
        return False


class PreEvaluationInline(admin.StackedInline):
    model = PreEvaluation
    extra = 0
    can_delete = False


class PostAutopsyInline(admin.StackedInline):
    model = PostAutopsy
    extra = 0
    can_delete = False


@admin.register(CaseSession)
class CaseSessionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'case', 'status', 'current_phase', 'priority',
        'nchs_score', 'n_interactions', 'mae_approved', 'mae', 'started_at', 'content_hash',
    )
    list_filter = ('status', 'current_phase', 'priority', 'mae_approved', 'sla_breached', 'abandonment_reason')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'case__title', 'content_hash')
    list_select_related = ('user', 'case', 'mae')
    date_hierarchy = 'started_at'
    readonly_fields = (
        'started_at', 'n_interactions', 'acumulado_ac', 'acumulado_sm', 'acumulado_ts',
        'nchs_score', 'content_hash',
    )
    inlines = [ChatMessageInline, PreEvaluationInline, PostAutopsyInline, CaseAuditInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'message_type', 'classification_variable', 'entropy_node', 'created_at')
    list_filter = ('role', 'message_type', 'classification_variable', 'entropy_node')
    search_fields = ('content', 'session__user__username', 'session__case__title')
    list_select_related = ('session', 'session__user', 'session__case')
    date_hierarchy = 'created_at'


class DiagnosisMessageInline(admin.TabularInline):
    model = DiagnosisMessage
    extra = 0
    can_delete = False
    fields = ('created_at', 'role', 'question_number', 'content')
    readonly_fields = fields
    ordering = ('created_at',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DiagnosisSession)
class DiagnosisSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'current_question', 'mae_approved', 'mae', 'started_at', 'completed_at')
    list_filter = ('status', 'mae_approved')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'mae')
    inlines = [DiagnosisMessageInline]


@admin.register(DiagnosisMessage)
class DiagnosisMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'question_number', 'created_at')
    list_filter = ('role',)
    search_fields = ('content', 'session__user__username')
    list_select_related = ('session', 'session__user')


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'academic_degree', 'institution_origin', 'is_active_tutor')
    list_filter = ('is_active_tutor',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'institution_origin')


@admin.register(AIConfiguration)
class AIConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'model_name', 'is_active', 'updated_at')
    list_filter = ('provider', 'is_active')


@admin.register(IAErrorLog)
class IAErrorLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'session', 'error_type', 'notified_admin', 'created_at')
    list_filter = ('error_type', 'notified_admin')
    search_fields = ('user__username', 'error_detail')
    readonly_fields = ('created_at',)


@admin.register(CaseAudit)
class CaseAuditAdmin(admin.ModelAdmin):
    list_display = ('session', 'user', 'action', 'previous_status', 'new_status', 'created_at')
    list_filter = ('action',)
    search_fields = ('session__user__username', 'session__case__title', 'observation')
    list_select_related = ('session', 'user')
    date_hierarchy = 'created_at'
