from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.FormaLoginView.as_view(), name='login'),
    path('logout/', views.FormaLogoutView.as_view(), name='logout'),
    path('logged-out/', TemplateView.as_view(template_name='accounts/logged_out.html'), name='logged_out'),
    path('register/', views.register, name='register'),
    path('password/change/', views.FormaPasswordChangeView.as_view(), name='password_change'),
    path(
        'cancel-subscription/',
        views.cancel_subscription_and_account,
        name='cancel_subscription',
    ),
    path('delete/', views.delete_account, name='delete_account'),
    path('deleted/', views.AccountDeletedView.as_view(), name='account_deleted'),
]
