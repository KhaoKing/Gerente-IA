from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import LoginForm, ManagerProfileForm
from .models import ManagerProfile


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_gerente and not user.profile_completed:
                return redirect('complete_profile')
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def complete_profile(request):
    if not request.user.is_gerente or request.user.profile_completed:
        return redirect('dashboard')
    try:
        instance = request.user.manager_profile
    except ManagerProfile.DoesNotExist:
        instance = None
    form = ManagerProfileForm(request.POST or None, instance=instance, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save(user=request.user)
        messages.success(request, '¡Perfil completado! Comenzaremos con tu diagnóstico inicial.')
        return redirect('dashboard')
    return render(request, 'accounts/complete_profile.html', {'form': form})
