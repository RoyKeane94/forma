from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('account/', views.my_account, name='my_account'),
    path('staff/forma-profiles/', views.staff_forma_profile_list, name='staff_forma_profiles'),
    path('staff/forma-profiles/new/', views.staff_forma_profile_create, name='staff_forma_profile_new'),
    path(
        'staff/forma-profiles/<int:profile_pk>/onboarding/edit/',
        views.staff_forma_onboarding_edit_start,
        name='staff_forma_onboarding_edit',
    ),
    path(
        'staff/forma-profiles/<int:profile_pk>/onboarding/edit/<int:step>/',
        views.staff_forma_onboarding_step_edit,
        name='staff_forma_onboarding_step_edit',
    ),
    path(
        'staff/forma-profiles/<int:profile_pk>/onboarding/',
        views.staff_forma_onboarding_redirect,
        name='staff_forma_onboarding',
    ),
    path(
        'staff/forma-profiles/<int:profile_pk>/onboarding/<int:step>/',
        views.staff_forma_onboarding_step,
        name='staff_forma_onboarding_step',
    ),
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
    path(
        '<slug:profile_slug>/<slug:url_key>/keep-profile/',
        views.keep_forma_profile_register,
        name='keep_forma_profile',
    ),
    path('<slug:profile_slug>/<slug:url_key>/', views.trainer_public_profile, name='trainer_profile_forma'),
    path('<slug:profile_slug>/', views.trainer_public_profile, name='trainer_profile'),
]
