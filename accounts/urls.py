from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('completar-perfil/', views.complete_profile, name='complete_profile'),
]
