import datetime

from django.contrib import admin
from django.contrib.admin.utils import display_for_field, display_for_value, label_for_field, lookup_field
from django.db import models as django_models
from django.http import HttpResponse
from django.utils.html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    ManagementCase, CaseSession, ChatMessage, DiagnosisSession, DiagnosisMessage,
    TeacherProfile, PreEvaluation, PostAutopsy, AIConfiguration, IAErrorLog, CaseAudit,
)


class PDFExportMixin:
    """Agrega una acción de admin que exporta la tabla visible (list_display) a PDF horizontal.

    `pdf_export_fields`, si se define, reemplaza a `list_display` como fuente de columnas
    del PDF (útil para incluir en el reporte campos de texto largo que no conviene mostrar
    en el listado del admin, como una descripción u observación).
    """

    pdf_export_fields = None

    @admin.action(description='Exportar seleccionados a PDF')
    def export_as_pdf(self, request, queryset):
        source_fields = self.pdf_export_fields or self.list_display
        field_names = [f for f in source_fields if f != 'action_checkbox']

        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            'PDFExportHeader', parent=styles['BodyText'],
            textColor=colors.white, fontName='Helvetica-Bold',
        )
        body_style = styles['BodyText']

        header_labels = []
        for field_name in field_names:
            try:
                header_labels.append(str(label_for_field(field_name, self.model, model_admin=self)).capitalize())
            except Exception:
                header_labels.append(field_name)

        rows = [[Paragraph(escape(label), header_style) for label in header_labels]]
        empty_value = self.get_empty_value_display()
        for obj in queryset:
            row = []
            for field_name in field_names:
                try:
                    field, attr, value = lookup_field(field_name, obj, self)
                except Exception:
                    row.append('—')
                    continue

                is_boolean = isinstance(field, django_models.BooleanField) or getattr(attr, 'boolean', False)
                if is_boolean:
                    # display_for_field()/display_for_value() render booleans as an <img> icon
                    # tag pointing at STATIC_URL, which reportlab's Paragraph parser can't handle.
                    text = empty_value if value is None else ('Sí' if value else 'No')
                elif field is not None:
                    text = display_for_field(value, field, empty_value)
                else:
                    text = display_for_value(value, empty_value, boolean=False)

                row.append(Paragraph(escape(str(text)), body_style))
            rows.append(row)

        response = HttpResponse(content_type='application/pdf')
        title = str(self.model._meta.verbose_name_plural)
        filename = f"{title}_{datetime.date.today()}.pdf".replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        left_margin = right_margin = top_margin = bottom_margin = 1 * cm
        doc = SimpleDocTemplate(
            response, pagesize=landscape(A4),
            leftMargin=left_margin, rightMargin=right_margin,
            topMargin=top_margin, bottomMargin=bottom_margin,
        )
        elements = [
            Paragraph(title.capitalize(), styles['Heading2']),
            Paragraph(f"Generado: {datetime.datetime.now():%d/%m/%Y %H:%M}", styles['Normal']),
            Spacer(1, 0.4 * cm),
        ]

        available_width = landscape(A4)[0] - left_margin - right_margin
        col_weights = []
        for field_name in field_names:
            if field_name == 'id':
                col_weights.append(0.5)
                continue
            try:
                model_field = self.model._meta.get_field(field_name)
            except Exception:
                model_field = None
            # Free-text fields (content, description, observation...) need much more
            # room to wrap in, or a long value can make a single row taller than the
            # page and crash the PDF build (ReportLab can't split a row across pages).
            col_weights.append(3.5 if isinstance(model_field, django_models.TextField) else 1.2)
        total_weight = sum(col_weights)
        col_widths = [available_width * w / total_weight for w in col_weights]
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        doc.build(elements)
        return response


@admin.register(ManagementCase)
class ManagementCaseAdmin(PDFExportMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'difficulty', 'priority', 'sla_hours', 'is_active')
    list_filter = ('category', 'difficulty', 'priority', 'is_active')
    search_fields = ('title', 'description')
    actions = ['export_as_pdf']
    pdf_export_fields = ('id', 'title', 'category', 'difficulty', 'priority', 'sla_hours', 'description')


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
class CaseSessionAdmin(PDFExportMixin, admin.ModelAdmin):
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
    actions = ['export_as_pdf']
    pdf_export_fields = (
        'id', 'diagnosis_chat_id', 'user', 'case', 'status', 'current_phase', 'priority',
        'nchs_score', 'n_interactions', 'mae', 'content_hash',
    )

    def diagnosis_chat_id(self, obj):
        diagnosis = getattr(obj.user, 'diagnosis_session', None)
        return diagnosis.id if diagnosis else None
    diagnosis_chat_id.short_description = 'ID Chat de Diagnóstico'


@admin.register(ChatMessage)
class ChatMessageAdmin(PDFExportMixin, admin.ModelAdmin):
    list_display = ('session', 'role', 'message_type', 'classification_variable', 'entropy_node', 'created_at')
    list_filter = ('role', 'message_type', 'classification_variable', 'entropy_node')
    search_fields = ('content', 'session__user__username', 'session__case__title')
    list_select_related = ('session', 'session__user', 'session__case')
    date_hierarchy = 'created_at'
    actions = ['export_as_pdf']
    pdf_export_fields = ('id', 'session', 'role', 'message_type', 'content', 'classification_variable', 'entropy_node', 'created_at')


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
class DiagnosisSessionAdmin(PDFExportMixin, admin.ModelAdmin):
    list_display = ('user', 'status', 'current_question', 'mae_approved', 'mae', 'started_at', 'completed_at')
    list_filter = ('status', 'mae_approved')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'mae')
    inlines = [DiagnosisMessageInline]
    actions = ['export_as_pdf']
    pdf_export_fields = ('id',) + list_display + ('mae_verdict',)


@admin.register(DiagnosisMessage)
class DiagnosisMessageAdmin(PDFExportMixin, admin.ModelAdmin):
    list_display = ('session', 'role', 'question_number', 'created_at')
    list_filter = ('role',)
    search_fields = ('content', 'session__user__username')
    list_select_related = ('session', 'session__user')
    actions = ['export_as_pdf']
    pdf_export_fields = ('id', 'chat_session_id', 'session', 'role', 'question_number', 'created_at')

    def chat_session_id(self, obj):
        return obj.session_id
    chat_session_id.short_description = 'ID Chat de Diagnóstico'


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
class CaseAuditAdmin(PDFExportMixin, admin.ModelAdmin):
    list_display = ('session', 'user', 'action', 'previous_status', 'new_status', 'created_at')
    list_filter = ('action',)
    search_fields = ('session__user__username', 'session__case__title', 'observation')
    list_select_related = ('session', 'user')
    date_hierarchy = 'created_at'
    actions = ['export_as_pdf']
    pdf_export_fields = ('id',) + list_display + ('observation',)
