from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, ManagerProfile


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'get_full_name', 'role', 'profile_completed', 'is_active')
    list_filter = ('role', 'profile_completed', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Rol y Perfil', {'fields': ('role', 'profile_completed')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rol', {'fields': ('role',)}),
    )


@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'position', 'company', 'level', 'diagnosis_completed')
    list_filter = ('level', 'industry', 'diagnosis_completed')
