from django.contrib import admin
from .models import ManagementCase, CaseSession, DiagnosisSession, IAErrorLog


@admin.register(ManagementCase)
class ManagementCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'difficulty', 'is_active')
    list_filter = ('category', 'difficulty', 'is_active')
    search_fields = ('title',)


@admin.register(CaseSession)
class CaseSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'case', 'status', 'mae_approved', 'started_at')
    list_filter = ('status', 'mae_approved')
    readonly_fields = ('started_at',)

@admin.register(DiagnosisSession)
class DiagnosisSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'current_question', 'mae_approved', 'mae', 'started_at')
    list_filter = ('status', 'mae_approved')

@admin.register(IAErrorLog)
class IAErrorLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'error_type', 'notified_admin', 'created_at')
    list_filter = ('error_type', 'notified_admin')
    readonly_fields = ('created_at',)
