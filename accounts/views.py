from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .forms import LoginForm, ManagerProfileForm, CreateUserForm, AdminMaeProfileForm, RegistrationForm
from .models import ManagerProfile


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if not user.profile_completed:
                return redirect('complete_profile')
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, '¡Registro completado! Bienvenido a Gerente IA.')
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def complete_profile(request):
    if request.user.profile_completed:
        return redirect('dashboard')

    if request.user.is_gerente:
        try:
            instance = request.user.manager_profile
        except ManagerProfile.DoesNotExist:
            instance = None
        form = ManagerProfileForm(request.POST or None, instance=instance, user=request.user)
        if request.method == 'POST' and form.is_valid():
            form.save(user=request.user)
            messages.success(request, '¡Perfil completado! Comenzaremos con tu diagnóstico inicial.')
            return redirect('dashboard')
    else:
        form = AdminMaeProfileForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            form.save(user=request.user)
            messages.success(request, '¡Perfil completado! Bienvenido a Gerente IA.')
            return redirect('dashboard')

    return render(request, 'accounts/complete_profile.html', {'form': form, 'is_admin_or_mae': not request.user.is_gerente})


@login_required
@user_passes_test(lambda u: u.is_admin_role)
def create_user(request):
    form = CreateUserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(
            request,
            f'Usuario "{user.username}" ({user.get_role_display()}) creado correctamente.'
        )
        return redirect('dashboard')
    return render(request, 'accounts/create_user.html', {'form': form})
