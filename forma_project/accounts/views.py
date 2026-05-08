import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView

from pages.models import TrainerProfile, ensure_onboarding_children
from pages.stripe_keep_profile import (
    cancel_stripe_subscription_immediately,
    save_checkout_billing_ids,
)

from .forms import (
    CancelSubscriptionDeleteAccountForm,
    DeleteAccountForm,
    FormaPasswordChangeForm,
    LoginForm,
    RegisterForm,
    RegisterNameForm,
)
from .models import Profile
from .media_cleanup import delete_user_and_associated_media
from .stripe_register import (
    checkout_session_metadata_dict,
    complete_pending_registration_from_stripe_session,
    create_register_checkout_session,
    delete_pending_registration,
    register_checkout_metadata_ok,
    retrieve_checkout_session,
    store_pending_registration,
    stripe_register_configured,
)

logger = logging.getLogger(__name__)


class FormaLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class FormaLogoutView(LogoutView):
    next_page = reverse_lazy('accounts:logged_out')


class FormaPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = FormaPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('pages:my_account')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been updated.')
        return super().form_valid(form)


class AccountDeletedView(TemplateView):
    template_name = 'accounts/account_deleted.html'


@login_required
def cancel_subscription_and_account(request):
    """Cancel Stripe subscription then delete the user (trainer profile + account)."""
    acc_profile, _ = Profile.objects.get_or_create(user=request.user)
    if not (acc_profile.stripe_subscription_id or '').strip():
        messages.info(
            request,
            'There is no active Forma subscription on this account. Use “Delete account” if you want to remove your account.',
        )
        return redirect('pages:my_account')

    if request.method == 'POST':
        form = CancelSubscriptionDeleteAccountForm(request.user, request.POST)
        if form.is_valid():
            sub_id = acc_profile.stripe_subscription_id.strip()
            ok, stripe_err = cancel_stripe_subscription_immediately(sub_id)
            if not ok:
                form.add_error(None, stripe_err or 'Could not cancel your subscription with Stripe.')
            else:
                user_to_delete = request.user
                logout(request)
                delete_user_and_associated_media(user_to_delete)
                messages.success(
                    request,
                    'Your subscription has been cancelled and your Forma account and trainer page have been removed.',
                )
                return redirect('accounts:account_deleted')
    else:
        form = CancelSubscriptionDeleteAccountForm(request.user)

    return render(
        request,
        'accounts/cancel_subscription.html',
        {'form': form},
    )


@login_required
def delete_account(request):
    if request.method == 'POST':
        form = DeleteAccountForm(request.user, request.POST)
        if form.is_valid():
            user_to_delete = request.user
            logout(request)
            delete_user_and_associated_media(user_to_delete)
            return redirect('accounts:account_deleted')
    else:
        form = DeleteAccountForm(request.user)
    return render(request, 'accounts/delete_account.html', {'form': form})


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.GET.get('checkout') == 'canceled':
        messages.info(request, 'Checkout was cancelled. Your account has not been charged.')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            if not stripe_register_configured():
                form.add_error(
                    None,
                    'Payments are not configured on this server. Add STRIPE_SK and STRIPE_PRICE_ID.',
                )
            else:
                pending_token = secrets.token_urlsafe(32)
                email = form.cleaned_data['email']
                store_pending_registration(
                    pending_token=pending_token,
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=email,
                    password=form.cleaned_data['password1'],
                )
                success_url = request.build_absolute_uri(
                    reverse('accounts:register_checkout_success'),
                ) + '?session_id={CHECKOUT_SESSION_ID}'
                cancel_url = request.build_absolute_uri(reverse('accounts:register')) + '?checkout=canceled'
                try:
                    checkout_url = create_register_checkout_session(
                        success_url=success_url,
                        cancel_url=cancel_url,
                        customer_email=email,
                        pending_token=pending_token,
                    )
                except Exception:
                    delete_pending_registration(pending_token)
                    form.add_error(
                        None,
                        'Could not start checkout. Check Stripe key and price configuration, then try again.',
                    )
                else:
                    return redirect(checkout_url)
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def register_checkout_success(request):
    if request.user.is_authenticated:
        return redirect('pages:my_account')

    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id or not stripe_register_configured():
        messages.error(request, 'Missing payment session. Please register again.')
        return redirect('accounts:register')

    try:
        stripe_session = retrieve_checkout_session(session_id)
    except Exception:
        messages.error(request, 'Could not verify payment. Please contact support.')
        return redirect('accounts:register')

    meta = checkout_session_metadata_dict(stripe_session)
    if not register_checkout_metadata_ok(meta):
        messages.error(request, 'This payment session is not valid for registration.')
        return redirect('accounts:register')

    user, err_msg = complete_pending_registration_from_stripe_session(stripe_session)
    if err_msg:
        messages.error(request, err_msg)
        return redirect('accounts:register')

    Profile.objects.get_or_create(user=user)
    save_checkout_billing_ids(user, stripe_session)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    _send_founder_welcome_email(request, user)
    messages.success(request, 'Welcome to Forma.')
    return redirect('pages:my_account')


def _ensure_trainer_profile_for_user(user):
    profile, _ = TrainerProfile.objects.get_or_create(
        user=user,
        defaults={
            'first_name': (user.first_name or '').strip(),
            'last_name': (user.last_name or '').strip(),
            'tagline': '',
            'bio': '',
        },
    )
    ensure_onboarding_children(profile)
    user_first = (user.first_name or '').strip()
    user_last = (user.last_name or '').strip()
    profile_first = (profile.first_name or '').strip()
    profile_last = (profile.last_name or '').strip()
    legacy_pairs = {
        ('Trainer', 'Profile'),
        ('Mark', 'Jobs'),
    }
    if not user_first and not user_last and (profile_first, profile_last) in legacy_pairs:
        profile.first_name = ''
        profile.last_name = ''
        profile.save(update_fields=['first_name', 'last_name'])
    return profile


def _send_founder_welcome_email(request, user) -> None:
    email = (user.email or '').strip()
    if not email:
        return
    profile = _ensure_trainer_profile_for_user(user)
    testimonial_link = request.build_absolute_uri(
        reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})
    )
    first_name = (user.first_name or '').strip() or 'there'
    message = f"""Hi {first_name},

Thanks for joining.

I built Forma because the best trainers I've seen lose clients they've already won - not because their work isn't good, but because there's nowhere credible for that work to land. Your Proof page fixes that.

One thing to do now: send your testimonial link to three clients you trust.

Your link: {testimonial_link}

Once those first videos come in, you have something worth sharing.

Reply to this email if you need anything. I read every one.

Tom
Founder, Forma"""
    try:
        send_mail(
            subject='Welcome to Forma',
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', ''),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send founder welcome email for user_id=%s', user.pk)


@login_required
def register_name(request):
    user = request.user
    profile = _ensure_trainer_profile_for_user(user)

    if request.method == 'POST':
        form = RegisterNameForm(request.POST)
        if form.is_valid():
            first = form.cleaned_data['first_name']
            last = form.cleaned_data['last_name']
            primary_area = form.cleaned_data['resolved_primary_area']
            user.first_name = first
            user.last_name = last
            user.save(update_fields=['first_name', 'last_name'])
            profile.first_name = first
            profile.last_name = last
            profile.primary_area = primary_area
            profile.save(update_fields=['first_name', 'last_name', 'primary_area'])
            messages.success(request, 'Name saved.')
            return redirect('accounts:register_name')
    else:
        form = RegisterNameForm(
            initial={
                'first_name': (user.first_name or profile.first_name or '').strip(),
                'last_name': (user.last_name or profile.last_name or '').strip(),
                'primary_area': profile.primary_area_id,
            }
        )

    proof_url = request.build_absolute_uri(
        reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})
    )
    names_ready = bool((user.first_name or '').strip() and (user.last_name or '').strip())
    return render(
        request,
        'accounts/register_name.html',
        {
            'form': form,
            'profile': profile,
            'proof_url': proof_url,
            'names_ready': names_ready,
        },
    )
