import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.forms import RegisterForm
from accounts.models import Profile as AccountsProfile

from .forms import (
    OnboardingStep1Form,
    TrainerWhoIWorkWithFormSet,
    OnboardingStep2QuickForm,
    OnboardingStep4Form,
    OnboardingStep5MetaForm,
    OnboardingStep6InstagramForm,
    OnboardingStep7ReviewsForm,
    StaffTrainerCreateForm,
    TrainerAdditionalQualificationFormSet,
    TrainerGalleryPhotoFormSet,
    PRICE_TIER_MAX_NUM,
    TrainerPriceTierFormSet,
    TrainerSpecialismFormSet,
    client_reviews_form_initial,
    price_tier_row_captions_for_meta_form,
)
from .models import QUICK_QUALIFICATION_CHOICES, TrainerProfile, ensure_onboarding_children
from .stripe_keep_profile import (
    checkout_session_paid,
    create_subscription_checkout_session,
    delete_pending_registration,
    peek_pending_registration,
    retrieve_checkout_session,
    save_checkout_billing_ids,
    store_pending_registration,
    stripe_configured,
)
from .onboarding_meta import ONBOARDING_STEPS, TAB_LABELS
from .profile_display import (
    areas_covered_count,
    non_empty_client_reviews,
    split_featured_client_reviews,
    visible_who_i_work_with_items,
    quick_qualification_items,
    specialism_display_items,
    training_location_items,
    visible_price_tiers,
)

STEP_COUNT = 7

logger = logging.getLogger(__name__)

_QUICK_QUAL_NOTE_MAX_LEN = 600


def _finalize_keep_forma_profile(*, profile_id: int, email: str, password: str):
    """
    Attach the Forma-made profile to a new user (or return existing user if already done).
    Returns (user, error_code). error_code is None on success.
    """
    User = get_user_model()
    email = (email or '').strip().lower()
    with transaction.atomic():
        profile = (
            TrainerProfile.objects.select_for_update()
            .select_related('user')
            .get(pk=profile_id)
        )
        if not profile.forma_made:
            existing = profile.user
            if (existing.email or '').strip().lower() == email:
                return existing, None
            return None, 'already_claimed'
        if User.objects.filter(email__iexact=email).exists():
            return None, 'email_taken'
        new_user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
        )
        AccountsProfile.objects.get_or_create(user=new_user)
        old_user = profile.user
        profile.user = new_user
        profile.forma_made = False
        profile.public_url_key = None
        profile.save()
        if old_user.pk != new_user.pk:
            old_user.delete()
        return new_user, None


def _stripe_metadata_dict(meta) -> dict:
    """Copy a Stripe metadata mapping to a plain str→str dict (never use dict(meta) on StripeObject)."""
    if meta is None:
        return {}
    if isinstance(meta, dict):
        return {str(k): '' if v is None else str(v) for k, v in meta.items()}
    to_dict = getattr(meta, 'to_dict', None)
    if callable(to_dict):
        try:
            raw = to_dict()
            if isinstance(raw, dict):
                return {str(k): '' if v is None else str(v) for k, v in raw.items()}
        except Exception:
            pass
    if hasattr(meta, 'items'):
        try:
            return {str(k): '' if v is None else str(v) for k, v in meta.items()}
        except Exception:
            pass
    out = {}
    for key in getattr(meta, 'keys', lambda: [])():
        try:
            out[str(key)] = '' if meta[key] is None else str(meta[key])
        except (KeyError, TypeError):
            continue
    return out


def _checkout_session_metadata_dict(stripe_session) -> dict:
    """Checkout Session.metadata via full session serialization (most reliable with StripeObject)."""
    to_dict = getattr(stripe_session, 'to_dict', None)
    if callable(to_dict):
        try:
            whole = to_dict()
            if isinstance(whole, dict):
                md = whole.get('metadata')
                if isinstance(md, dict):
                    return {str(k): '' if v is None else str(v) for k, v in md.items()}
        except Exception:
            pass
    return _stripe_metadata_dict(getattr(stripe_session, 'metadata', None))


def _keep_profile_checkout_metadata_ok(meta: dict) -> bool:
    """Sessions we create set purpose=keep_profile; tolerate missing purpose if token+profile are set."""
    if not meta:
        return False
    if (meta.get('purpose') or '').strip() == 'keep_profile':
        return True
    return bool((meta.get('pending_token') or '').strip() and (meta.get('profile_id') or '').strip())


def _complete_keep_profile_from_stripe_session(*, profile: TrainerProfile, stripe_session) -> tuple:
    """
    After a paid Checkout Session, create the account if pending data exists.
    Returns (user | None, error_message for display).
    """
    if not checkout_session_paid(stripe_session):
        return None, 'Payment was not completed. Please try again or contact support.'

    meta = _checkout_session_metadata_dict(stripe_session)
    try:
        meta_profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        meta_profile_id = 0
    if meta_profile_id != profile.pk:
        return None, 'This payment does not match this profile page.'

    pending_token = (meta.get('pending_token') or '').strip()
    if not pending_token:
        if not profile.forma_made:
            return profile.user, None
        return None, 'Your registration data expired. Please start again from the form.'

    data = peek_pending_registration(pending_token)
    if not data:
        if not profile.forma_made:
            return profile.user, None
        return None, 'Your registration data expired. Please start again from the form.'

    if int(data.get('profile_id') or 0) != profile.pk:
        return None, 'Something went wrong linking your payment. Please contact support.'

    user, err = _finalize_keep_forma_profile(
        profile_id=profile.pk,
        email=data['email'],
        password=data['password'],
    )
    if err == 'email_taken':
        delete_pending_registration(pending_token)
        return None, 'That email is already registered. Sign in, or contact support if you were charged.'
    if err == 'already_claimed':
        delete_pending_registration(pending_token)
        return None, 'This profile has already been claimed.'
    if user is None:
        return None, 'We could not finish creating your account. Please contact support.'

    delete_pending_registration(pending_token)
    return user, None


def _quick_qual_notes_from_post(request) -> dict:
    out = {}
    allowed = {k for k, _ in QUICK_QUALIFICATION_CHOICES}
    for key in allowed:
        raw = (request.POST.get(f'quick_qual_note_{key}') or '').strip()
        if raw:
            out[key] = raw[:_QUICK_QUAL_NOTE_MAX_LEN]
    return out


def _get_profile(user) -> TrainerProfile:
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
    return profile


def _advance_profile(profile: TrainerProfile, step_idx: int) -> None:
    if step_idx < STEP_COUNT - 1:
        profile.onboarding_step = step_idx + 1
        profile.save(update_fields=['onboarding_step'])
    else:
        profile.onboarding_step = STEP_COUNT
        profile.completed_at = timezone.now()
        profile.save(update_fields=['onboarding_step', 'completed_at'])


@login_required
def my_account(request):
    profile = _get_profile(request.user)
    accounts_profile, _ = AccountsProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST' and request.POST.get('update_visibility'):
        profile.is_published = request.POST.get('is_published') == 'on'
        profile.save(update_fields=['is_published'])
        if profile.is_published:
            messages.success(request, 'Your page is now published — your public link works for everyone.')
        else:
            messages.success(request, 'Your page is unpublished — only you can open your profile link while signed in.')
        return redirect('pages:my_account')

    public_profile_url = ''
    if profile.completed_at and profile.is_published:
        public_profile_url = request.build_absolute_uri(profile.get_absolute_url())

    return render(
        request,
        'pages/my_account.html',
        {
            'profile': profile,
            'accounts_profile': accounts_profile,
            'tab_labels': TAB_LABELS,
            'public_profile_url': public_profile_url,
        },
    )


@login_required
def onboarding_edit_start(request):
    profile = _get_profile(request.user)
    if not profile.completed_at:
        return redirect('pages:onboarding')
    return redirect('pages:onboarding_step_edit', step=1)


@login_required
def onboarding_redirect(request):
    profile = _get_profile(request.user)
    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:onboarding_complete')
    return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)


def _onboarding_redirect(step: int, *, onboarding_edit: bool, staff_forma: bool, profile_pk: int | None):
    if staff_forma and profile_pk is not None:
        if onboarding_edit:
            return redirect('pages:staff_forma_onboarding_step_edit', profile_pk=profile_pk, step=step)
        return redirect('pages:staff_forma_onboarding_step', profile_pk=profile_pk, step=step)
    if onboarding_edit:
        return redirect('pages:onboarding_step_edit', step=step)
    return redirect('pages:onboarding_step', step=step)


def _onboarding_step_for_profile(
    request,
    profile: TrainerProfile,
    step: int,
    *,
    onboarding_edit: bool,
    staff_forma: bool,
):
    if not 1 <= step <= STEP_COUNT:
        raise Http404
    step_idx = step - 1

    if not staff_forma and onboarding_edit and not profile.completed_at:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

    if staff_forma and onboarding_edit and not profile.completed_at:
        return redirect('pages:staff_forma_onboarding_step', profile_pk=profile.pk, step=profile.onboarding_step + 1)

    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        if staff_forma and not onboarding_edit:
            messages.info(request, 'This profile is already complete.')
            return redirect('pages:staff_forma_profiles')
        if not staff_forma and not onboarding_edit:
            return redirect('pages:onboarding_complete')

    if not onboarding_edit and not staff_forma and step_idx > profile.onboarding_step:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

    skip_advance = bool(onboarding_edit and profile.completed_at)
    max_reachable_step = STEP_COUNT if onboarding_edit else profile.onboarding_step + 1

    context = {
        'step': step_idx,
        'step_display': step,
        'prev_step': step - 1 if step > 1 else None,
        'profile': profile,
        'total_steps': STEP_COUNT,
        'tab_labels': TAB_LABELS,
        'step_meta': ONBOARDING_STEPS[step_idx],
        'max_reachable_step': max_reachable_step,
        'onboarding_edit': onboarding_edit,
        'staff_forma': staff_forma,
        'staff_profile_pk': profile.pk if staff_forma else None,
    }

    profile_pk = profile.pk if staff_forma else None

    if request.method == 'POST':
        advance = not request.POST.get('save_draft')
        ok, errors = _process_step_post(
            request,
            profile,
            step_idx,
            advance=advance,
            skip_profile_advance=skip_advance,
        )
        if ok:
            if not advance:
                messages.success(request, 'Draft saved.')
                return _onboarding_redirect(step, onboarding_edit=onboarding_edit, staff_forma=staff_forma, profile_pk=profile_pk)
            if step_idx == STEP_COUNT - 1:
                if onboarding_edit:
                    if staff_forma:
                        messages.success(request, 'Profile updated.')
                        return redirect('pages:staff_forma_profiles')
                    messages.success(request, 'Your page has been updated.')
                    return redirect(profile)
                if staff_forma:
                    messages.success(request, 'Forma-made profile is complete.')
                    return redirect('pages:staff_forma_profiles')
                return redirect('pages:onboarding_complete')
            return _onboarding_redirect(step + 1, onboarding_edit=onboarding_edit, staff_forma=staff_forma, profile_pk=profile_pk)
        messages.error(request, 'Please correct the errors below.')
        context.update(errors)
    else:
        _load_step_get_forms(context, profile, step_idx)

    return render(request, 'pages/onboarding.html', context)


@login_required
def onboarding_step(request, step: int, onboarding_edit: bool = False):
    profile = _get_profile(request.user)
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=onboarding_edit,
        staff_forma=False,
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_profile_list(request):
    profiles = (
        TrainerProfile.objects.filter(forma_made=True, created_by=request.user)
        .select_related('user')
        .order_by('-pk')
    )
    rows = []
    for p in profiles:
        url = request.build_absolute_uri(p.get_absolute_url()) if p.public_url_key else ''
        rows.append(
            {
                'profile': p,
                'label': f'{p.first_name} {p.last_name}'.strip(),
                'url': url,
            }
        )
    return render(
        request,
        'pages/staff_forma_profile_list.html',
        {'rows': rows},
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_profile_create(request):
    if request.method == 'POST':
        form = StaffTrainerCreateForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            username_max = User._meta.get_field('username').max_length
            uname = f"forma_{secrets.token_hex(8)}"
            while User.objects.filter(username=uname).exists():
                uname = f"forma_{secrets.token_hex(8)}"
            email = f"{uname}@placeholder.forma"
            user = User(
                username=uname[:username_max],
                email=email,
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                is_active=False,
            )
            user.set_unusable_password()
            user.save()
            AccountsProfile.objects.get_or_create(user=user)
            profile = TrainerProfile(
                user=user,
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                tagline='',
                bio='',
                forma_made=True,
                created_by=request.user,
                is_published=True,
            )
            profile.save()
            ensure_onboarding_children(profile)
            messages.success(request, 'Profile created. Complete the onboarding steps.')
            return redirect('pages:staff_forma_onboarding', profile_pk=profile.pk)
    else:
        form = StaffTrainerCreateForm()
    return render(
        request,
        'pages/staff_forma_profile_new.html',
        {'form': form},
    )


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def staff_forma_profile_delete(request, profile_pk: int):
    """Remove a Forma-made profile and its placeholder user (superuser-only, own creations)."""
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    label = f'{profile.first_name} {profile.last_name}'.strip() or profile.user.get_username()
    user = profile.user
    with transaction.atomic():
        user.delete()
    messages.success(request, f'Deleted profile for {label}.')
    return redirect('pages:staff_forma_profiles')


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_redirect(request, profile_pk: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:staff_forma_profiles')
    return redirect('pages:staff_forma_onboarding_step', profile_pk=profile.pk, step=profile.onboarding_step + 1)


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_step(request, profile_pk: int, step: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=False,
        staff_forma=True,
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_edit_start(request, profile_pk: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    if not profile.completed_at:
        return redirect('pages:staff_forma_onboarding', profile_pk=profile_pk)
    return redirect('pages:staff_forma_onboarding_step_edit', profile_pk=profile_pk, step=1)


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_step_edit(request, profile_pk: int, step: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=True,
        staff_forma=True,
    )


@login_required
def onboarding_complete(request):
    profile = _get_profile(request.user)
    if not profile.completed_at:
        return redirect('pages:onboarding')
    return render(request, 'pages/onboarding_complete.html', {'profile': profile})


def trainer_profile_id_redirect(request, profile_id: int):
    profile = get_object_or_404(TrainerProfile, pk=profile_id)
    return redirect(profile, permanent=True)


def keep_forma_profile_register(request, profile_slug: str, url_key: str):
    """
    Forma-made public profiles: collect email/password, then Stripe Checkout.
    The account is created only after payment (success page or webhook).
    """
    if len(url_key) != 5:
        raise Http404
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('user', 'primary_area'),
        slug__iexact=profile_slug,
        public_url_key__iexact=url_key,
        forma_made=True,
    )
    if not profile.is_published:
        raise Http404
    if request.user.is_authenticated:
        messages.info(
            request,
            'You’re signed in. Sign out first if you need to claim this page with a different account.',
        )
        return redirect('pages:my_account')

    if request.GET.get('checkout') == 'canceled':
        messages.info(request, 'Checkout was cancelled. Your account has not been charged.')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            if not stripe_configured():
                form.add_error(
                    None,
                    'Payments are not configured on this server. Add Stripe keys to the environment.',
                )
            else:
                pending_token = secrets.token_urlsafe(32)
                email = form.cleaned_data['email']
                password = form.cleaned_data['password1']
                store_pending_registration(
                    pending_token=pending_token,
                    profile_id=profile.pk,
                    email=email,
                    password=password,
                )
                success_url = request.build_absolute_uri(
                    reverse('pages:keep_forma_profile_success'),
                ) + '?session_id={CHECKOUT_SESSION_ID}'
                cancel_url = request.build_absolute_uri(
                    reverse(
                        'pages:keep_forma_profile',
                        kwargs={
                            'profile_slug': profile.slug,
                            'url_key': profile.public_url_key,
                        },
                    )
                ) + '?checkout=canceled'
                try:
                    checkout_url = create_subscription_checkout_session(
                        success_url=success_url,
                        cancel_url=cancel_url,
                        customer_email=email,
                        pending_token=pending_token,
                        profile_id=profile.pk,
                    )
                except Exception:
                    logger.exception('Stripe Checkout failed for keep-profile')
                    delete_pending_registration(pending_token)
                    form.add_error(
                        None,
                        'Could not start checkout. Check Stripe product/price configuration and try again.',
                    )
                else:
                    return redirect(checkout_url)
    else:
        form = RegisterForm()

    return render(
        request,
        'pages/keep_profile_register.html',
        {'form': form, 'profile': profile},
    )


def keep_forma_profile_checkout_success(request):
    """
    Stripe redirects here with ?session_id=… — profile is identified from Checkout metadata
    (the vanity URL key is cleared after claim, so we cannot use /slug/key/ for this step).
    """
    if request.user.is_authenticated:
        return redirect('pages:my_account')

    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id or not stripe_configured():
        messages.error(request, 'Missing payment session. Please open your profile link and try again.')
        return redirect('pages:my_account')

    try:
        stripe_session = retrieve_checkout_session(session_id)
    except Exception:
        logger.exception('Could not retrieve Stripe session')
        messages.error(request, 'Could not verify payment. Please contact support.')
        return redirect('pages:my_account')

    meta = _checkout_session_metadata_dict(stripe_session)
    if not _keep_profile_checkout_metadata_ok(meta):
        messages.error(request, 'This payment session is not valid for profile signup.')
        return redirect('pages:my_account')

    try:
        profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        profile_id = 0
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('user', 'primary_area'),
        pk=profile_id,
    )
    if not profile.is_published:
        raise Http404

    user, err_msg = _complete_keep_profile_from_stripe_session(
        profile=profile,
        stripe_session=stripe_session,
    )
    if err_msg:
        messages.error(request, err_msg)
        return redirect('pages:my_account')

    if user is not None:
        save_checkout_billing_ids(user, stripe_session)

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(
        request,
        'Your account is ready — this profile is now yours. Your public link has been updated.',
    )
    return redirect('pages:my_account')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Optional: completes keep-profile signup if the customer closes the tab before the success URL."""
    secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '') or ''
    if not secret.strip():
        return HttpResponse(status=404)

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        return HttpResponseBadRequest('invalid payload')
    except stripe.error.SignatureVerificationError:
        return HttpResponseBadRequest('invalid signature')

    if event['type'] != 'checkout.session.completed':
        return HttpResponse(status=200)

    session = event['data']['object']
    meta = session.get('metadata') or {}
    if not isinstance(meta, dict):
        meta = _stripe_metadata_dict(meta)
    if not _keep_profile_checkout_metadata_ok(meta):
        return HttpResponse(status=200)

    try:
        profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        return HttpResponse(status=200)

    profile = TrainerProfile.objects.filter(pk=profile_id, forma_made=True).select_related('user').first()
    if profile is None:
        profile = TrainerProfile.objects.filter(pk=profile_id).first()
        if profile is None:
            return HttpResponse(status=200)
        if not profile.forma_made:
            return HttpResponse(status=200)

    try:
        stripe_session = retrieve_checkout_session(session['id'])
    except Exception:
        logger.exception('Webhook could not reload checkout session')
        return HttpResponse(status=500)

    user, err_msg = _complete_keep_profile_from_stripe_session(
        profile=profile,
        stripe_session=stripe_session,
    )
    if user is not None:
        save_checkout_billing_ids(user, stripe_session)
    if err_msg and user is None:
        logger.warning('Stripe webhook keep-profile incomplete: %s', err_msg)
    return HttpResponse(status=200)


def trainer_public_profile(request, profile_slug: str, url_key: str | None = None):
    if url_key is not None and len(url_key) != 5:
        raise Http404
    qs = TrainerProfile.objects.select_related(
        'user',
        'primary_area__district',
    ).prefetch_related(
        'additional_qualifications',
        'specialisms',
        'price_tiers',
        'gallery_photos',
        'who_i_work_with_items',
    )
    if url_key is not None:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            public_url_key__iexact=url_key,
            forma_made=True,
        )
    else:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            forma_made=False,
        )
    is_owner = request.user.is_authenticated and request.user.pk == profile.user_id
    is_forma_creator = (
        request.user.is_authenticated
        and request.user.is_superuser
        and profile.forma_made
        and profile.created_by_id == request.user.pk
    )
    # Owner or creating superuser: may preview drafts (unpublished or onboarding incomplete).
    # Everyone else: self-serve profiles need completed onboarding + published; Forma-made
    # only needs published (completed_at is still unset until step 7 — staff would otherwise
    # see a live URL that 404s for clients).
    if not is_owner and not is_forma_creator:
        if not profile.is_published:
            raise Http404
        if not profile.forma_made and not profile.completed_at:
            raise Http404

    ig_handle = (profile.instagram_handle or '').strip().lstrip('@')
    instagram_url = f'https://www.instagram.com/{ig_handle}/' if ig_handle else ''

    review_rows = non_empty_client_reviews(profile)
    featured_review, other_reviews = split_featured_client_reviews(profile, review_rows)
    review_stats = None
    if review_rows:
        n = len(review_rows)
        total = sum(int(r['rating']) for r in review_rows)
        review_stats = {
            'count': n,
            'average': round(total / n, 1),
        }

    price_tiers = visible_price_tiers(profile)

    context = {
        'profile': profile,
        'quick_qual_items': quick_qualification_items(profile),
        'training_location_items': training_location_items(profile.training_locations),
        'featured_review': featured_review,
        'other_reviews': other_reviews,
        'specialism_items': specialism_display_items(profile),
        'price_tiers': price_tiers,
        'review_stats': review_stats,
        'instagram_url': instagram_url,
        'who_i_work_with_items': visible_who_i_work_with_items(profile),
        'areas_covered_count': areas_covered_count(profile),
    }
    return render(request, 'pages/trainer_profile.html', context)


def _pricing_row_has_content(cleaned: dict | None) -> bool:
    if not cleaned:
        return False
    label = (cleaned.get('label') or '').strip()
    has_price = cleaned.get('price') is not None
    return bool(label or has_price)


def _pricing_most_popular_row_ok(meta, pfs) -> bool:
    """Requires meta and formset to have already passed is_valid()."""
    cd = meta.cleaned_data
    if not cd.get('show_most_popular_tier'):
        return True
    raw = (cd.get('most_popular_row') or '').strip()
    if not raw.isdigit():
        return True
    idx = int(raw)
    if idx < 0 or idx >= len(pfs.forms):
        meta.add_error('most_popular_row', 'Choose a valid price row.')
        return False
    form = pfs.forms[idx]
    fcd = getattr(form, 'cleaned_data', None) or {}
    if not _pricing_row_has_content(fcd):
        meta.add_error(
            'most_popular_row',
            'Pick a row that already has a label or a price filled in.',
        )
        return False
    return True


def _pricing_step_show_add_button(formset) -> bool:
    return len(formset.forms) < PRICE_TIER_MAX_NUM


def _apply_pricing_most_popular(profile: TrainerProfile, meta_cleaned: dict) -> None:
    profile.price_tiers.filter(order__lte=10).update(is_most_popular=False)
    if not meta_cleaned.get('show_most_popular_tier'):
        return
    raw = (meta_cleaned.get('most_popular_row') or '').strip()
    if not raw.isdigit():
        return
    idx = int(raw)
    tiers = list(profile.price_tiers.filter(order__lte=10).order_by('order'))
    if not (0 <= idx < len(tiers)):
        return
    t = tiers[idx]
    if _pricing_row_has_content({'label': t.label, 'price': t.price}):
        t.is_most_popular = True
        t.save(update_fields=['is_most_popular'])


def _process_step_post(
    request,
    profile: TrainerProfile,
    step_idx: int,
    *,
    advance: bool = True,
    skip_profile_advance: bool = False,
) -> tuple[bool, dict]:
    def _advance_if_needed() -> None:
        if advance and not skip_profile_advance:
            _advance_profile(profile, step_idx)

    if step_idx == 0:
        ensure_onboarding_children(profile)
        form = OnboardingStep1Form(request.POST, request.FILES, instance=profile)
        wfs = TrainerWhoIWorkWithFormSet(request.POST, instance=profile)
        form_ok = form.is_valid()
        wfs_ok = wfs.is_valid()
        if form_ok and wfs_ok:
            form.save()
            wfs.save()
            _advance_if_needed()
            return True, {}
        return False, {'form': form, 'who_formset': wfs}

    if step_idx == 1:
        quick = OnboardingStep2QuickForm(request.POST)
        fs = TrainerAdditionalQualificationFormSet(request.POST, instance=profile)
        if quick.is_valid() and fs.is_valid():
            selected = list(quick.cleaned_data.get('quick_qualifications') or [])
            profile.quick_qualifications = selected
            notes = _quick_qual_notes_from_post(request)
            profile.quick_qualification_notes = {k: notes[k] for k in selected if k in notes}
            profile.save(update_fields=['quick_qualifications', 'quick_qualification_notes'])
            fs.save()
            _advance_if_needed()
            return True, {}
        post_notes = _quick_qual_notes_from_post(request)
        return False, {
            'quick_form': quick,
            'formset': fs,
            'quick_qual_selected': list(request.POST.getlist('quick_qualifications')),
            'quick_qual_note_rows': [
                {'key': k, 'label': lab, 'text': post_notes.get(k, '')}
                for k, lab in QUICK_QUALIFICATION_CHOICES
            ],
        }

    if step_idx == 2:
        fs = TrainerSpecialismFormSet(request.POST, instance=profile)
        if fs.is_valid():
            fs.save()
            _advance_if_needed()
            return True, {}
        return False, {'formset': fs}

    if step_idx == 3:
        form = OnboardingStep4Form(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            _advance_if_needed()
            return True, {}
        return False, {'form': form}

    if step_idx == 4:
        pfs = TrainerPriceTierFormSet(request.POST, instance=profile)
        meta = OnboardingStep5MetaForm(
            request.POST,
            instance=profile,
            tier_row_captions=price_tier_row_captions_for_meta_form(pfs),
        )
        ok_pfs = pfs.is_valid()
        ok_meta = meta.is_valid()
        if ok_pfs and ok_meta and not _pricing_most_popular_row_ok(meta, pfs):
            ok_meta = False
        if ok_pfs and ok_meta:
            meta.save()
            pfs.save()
            _apply_pricing_most_popular(profile, meta.cleaned_data)
            _advance_if_needed()
            return True, {}
        return False, {
            'meta_form': meta,
            'formset': pfs,
            'price_tier_show_add_button': _pricing_step_show_add_button(pfs),
        }

    if step_idx == 5:
        ig = OnboardingStep6InstagramForm(request.POST, instance=profile)
        gfs = TrainerGalleryPhotoFormSet(request.POST, request.FILES, instance=profile)
        if ig.is_valid() and gfs.is_valid():
            ig.save()
            gfs.save()
            _advance_if_needed()
            return True, {}
        return False, {'instagram_form': ig, 'formset': gfs}

    if step_idx == 6:
        rf = OnboardingStep7ReviewsForm(request.POST, profile=profile)
        if rf.is_valid():
            rf.save_to_profile(profile)
            _advance_if_needed()
            return True, {}
        return False, {'reviews_form': rf}

    return False, {}


def _load_step_get_forms(context: dict, profile: TrainerProfile, step_idx: int) -> None:
    if step_idx == 0:
        ensure_onboarding_children(profile)
        context['form'] = OnboardingStep1Form(instance=profile)
        context['who_formset'] = TrainerWhoIWorkWithFormSet(instance=profile)
    elif step_idx == 1:
        context['quick_form'] = OnboardingStep2QuickForm(
            initial={'quick_qualifications': profile.quick_qualifications or []}
        )
        context['formset'] = TrainerAdditionalQualificationFormSet(instance=profile)
        notes = dict(profile.quick_qualification_notes or {})
        context['quick_qual_selected'] = list(profile.quick_qualifications or [])
        context['quick_qual_note_rows'] = [
            {'key': k, 'label': lab, 'text': (notes.get(k) or '')}
            for k, lab in QUICK_QUALIFICATION_CHOICES
        ]
    elif step_idx == 2:
        context['formset'] = TrainerSpecialismFormSet(instance=profile)
    elif step_idx == 3:
        context['form'] = OnboardingStep4Form(instance=profile)
    elif step_idx == 4:
        fs = TrainerPriceTierFormSet(instance=profile)
        context['formset'] = fs
        context['meta_form'] = OnboardingStep5MetaForm(
            instance=profile,
            tier_row_captions=price_tier_row_captions_for_meta_form(fs),
        )
        context['price_tier_show_add_button'] = _pricing_step_show_add_button(fs)
    elif step_idx == 5:
        context['instagram_form'] = OnboardingStep6InstagramForm(instance=profile)
        context['formset'] = TrainerGalleryPhotoFormSet(instance=profile)
    elif step_idx == 6:
        context['reviews_form'] = OnboardingStep7ReviewsForm(
            initial=client_reviews_form_initial(profile),
            profile=profile,
        )
