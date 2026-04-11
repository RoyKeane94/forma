import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Profile as AccountsProfile

from .forms import (
    OnboardingStep1Form,
    OnboardingStep2QuickForm,
    OnboardingStep4Form,
    OnboardingStep5MetaForm,
    OnboardingStep6InstagramForm,
    OnboardingStep7ReviewsForm,
    StaffTrainerCreateForm,
    TrainerAdditionalQualificationFormSet,
    TrainerGalleryPhotoFormSet,
    TrainerPriceTierFormSet,
    TrainerSpecialismFormSet,
    client_reviews_form_initial,
)
from .models import TrainerProfile, ensure_onboarding_children
from .onboarding_meta import ONBOARDING_STEPS, TAB_LABELS
from .profile_display import (
    non_empty_additional_qualifications,
    non_empty_client_reviews,
    non_empty_specialisms,
    quick_qualification_labels,
    training_location_items,
    visible_price_tiers,
)

STEP_COUNT = 7


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
        'onboarding_steps': ONBOARDING_STEPS,
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
    if not is_owner and not is_forma_creator:
        if not profile.completed_at or not profile.is_published:
            raise Http404

    specs = non_empty_specialisms(profile)
    nav_spec = ''
    if specs:
        nav_spec = ' · '.join(specs[:2])
    if profile.postcode_district:
        nav_spec = f'{nav_spec} · {profile.postcode_district}' if nav_spec else profile.postcode_district

    initials = ''
    if profile.first_name:
        initials += profile.first_name[0].upper()
    if profile.last_name:
        initials += profile.last_name[0].upper()

    ig_handle = (profile.instagram_handle or '').strip().lstrip('@')
    instagram_url = f'https://www.instagram.com/{ig_handle}/' if ig_handle else ''

    context = {
        'profile': profile,
        'quick_qual_labels': quick_qualification_labels(profile.quick_qualifications),
        'training_location_items': training_location_items(profile.training_locations),
        'additional_quals': non_empty_additional_qualifications(profile),
        'client_reviews': non_empty_client_reviews(profile),
        'specialisms': specs,
        'price_tiers': visible_price_tiers(profile),
        'nav_spec_line': nav_spec,
        'initials_watermark': initials or '·',
        'instagram_url': instagram_url,
    }
    return render(request, 'pages/trainer_profile.html', context)


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
        form = OnboardingStep1Form(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            _advance_if_needed()
            return True, {}
        return False, {'form': form}

    if step_idx == 1:
        quick = OnboardingStep2QuickForm(request.POST)
        fs = TrainerAdditionalQualificationFormSet(request.POST, instance=profile)
        if quick.is_valid() and fs.is_valid():
            profile.quick_qualifications = list(quick.cleaned_data.get('quick_qualifications') or [])
            profile.save(update_fields=['quick_qualifications'])
            fs.save()
            _advance_if_needed()
            return True, {}
        return False, {'quick_form': quick, 'formset': fs}

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
        meta = OnboardingStep5MetaForm(request.POST, instance=profile)
        pfs = TrainerPriceTierFormSet(request.POST, instance=profile)
        if meta.is_valid() and pfs.is_valid():
            meta.save()
            pfs.save()
            _advance_if_needed()
            return True, {}
        return False, {'meta_form': meta, 'formset': pfs}

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
        context['form'] = OnboardingStep1Form(instance=profile)
    elif step_idx == 1:
        context['quick_form'] = OnboardingStep2QuickForm(
            initial={'quick_qualifications': profile.quick_qualifications or []}
        )
        context['formset'] = TrainerAdditionalQualificationFormSet(instance=profile)
    elif step_idx == 2:
        context['formset'] = TrainerSpecialismFormSet(instance=profile)
    elif step_idx == 3:
        context['form'] = OnboardingStep4Form(instance=profile)
    elif step_idx == 4:
        context['meta_form'] = OnboardingStep5MetaForm(instance=profile)
        context['formset'] = TrainerPriceTierFormSet(instance=profile)
    elif step_idx == 5:
        context['instagram_form'] = OnboardingStep6InstagramForm(instance=profile)
        context['formset'] = TrainerGalleryPhotoFormSet(instance=profile)
    elif step_idx == 6:
        context['reviews_form'] = OnboardingStep7ReviewsForm(
            initial=client_reviews_form_initial(profile),
            profile=profile,
        )
