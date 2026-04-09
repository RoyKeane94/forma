from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('onboarding/', views.onboarding_redirect, name='onboarding'),
    path('onboarding/complete/', views.onboarding_complete, name='onboarding_complete'),
    path('onboarding/<int:step>/', views.onboarding_step, name='onboarding_step'),
]
