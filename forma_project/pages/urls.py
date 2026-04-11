from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('account/', views.my_account, name='my_account'),
    path('onboarding/', views.onboarding_redirect, name='onboarding'),
    path('onboarding/edit/', views.onboarding_edit_start, name='onboarding_edit'),
    path(
        'onboarding/edit/<int:step>/',
        views.onboarding_step,
        {'onboarding_edit': True},
        name='onboarding_step_edit',
    ),
    path('onboarding/complete/', views.onboarding_complete, name='onboarding_complete'),
    path('onboarding/<int:step>/', views.onboarding_step, name='onboarding_step'),
    path('trainer/<int:profile_id>/', views.trainer_profile_id_redirect, name='trainer_profile_legacy'),
    path('<slug:profile_slug>/', views.trainer_public_profile, name='trainer_profile'),
]
