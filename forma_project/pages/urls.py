from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = 'pages'

urlpatterns = [
    path(
        'legal/privacy/',
        TemplateView.as_view(template_name='pages/legal/privacy.html'),
        name='privacy',
    ),
    path(
        'legal/terms/',
        TemplateView.as_view(template_name='pages/legal/terms.html'),
        name='terms',
    ),
    path('enquire/', views.profile_enquiry, name='profile_enquiry'),
    path('account/', views.my_account, name='my_account'),
    path('account/notifications/', views.proof_notifications, name='proof_notifications'),
    path('account/proof/', views.proof_testimonials_page, name='proof_testimonials_page'),
    path('account/testimonials/', views.proof_testimonials_page),
    path(
        'keep-profile-return/',
        views.keep_forma_profile_checkout_success,
        name='keep_forma_profile_success',
    ),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('track/pageview/', views.track_profile_pageview, name='track_profile_pageview'),
    path('track/scroll/', views.track_profile_scroll, name='track_profile_scroll'),
    path('staff/forma-profiles/', views.staff_forma_profile_list, name='staff_forma_profiles'),
    path(
        'staff/forma-profiles/reset-analytics/',
        views.staff_forma_profile_reset_analytics,
        name='staff_forma_profile_reset_analytics',
    ),
    path(
        'staff/forma-profiles/<int:profile_pk>/outreach/',
        views.staff_forma_outreach_toggle,
        name='staff_forma_outreach_toggle',
    ),
    path(
        'staff/forma-profiles/new/yaml/',
        views.staff_forma_profile_create_yaml,
        name='staff_forma_profile_new_yaml',
    ),
    path('staff/forma-profiles/new/', views.staff_forma_profile_create, name='staff_forma_profile_new'),
    path(
        'staff/forma-profiles/<int:profile_pk>/delete/',
        views.staff_forma_profile_delete,
        name='staff_forma_profile_delete',
    ),
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
    path('<slug:profile_slug>/proof/success/', views.trainer_proof_submit_success, name='trainer_proof_submit_success'),
    path('<slug:profile_slug>/proof/', views.trainer_proof_submit, name='trainer_proof_submit'),
    path(
        '<slug:profile_slug>/<slug:url_key>/keep-profile/',
        views.keep_forma_profile_register,
        name='keep_forma_profile',
    ),
    path('<slug:profile_slug>/<slug:url_key>/', views.trainer_public_profile, name='trainer_profile_forma'),
    path('<slug:profile_slug>/', views.trainer_public_profile, name='trainer_profile'),
]
