from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AREAS,
    OnboardingStep1Form,
    OnboardingStep2QuickForm,
    OnboardingStep4Form,
    OnboardingStep5MetaForm,
    OnboardingStep6InstagramForm,
    TrainerAdditionalQualificationFormSet,
    TrainerGalleryPhotoFormSet,
    TrainerPriceTierFormSet,
    TrainerSpecialismFormSet,
)
from .models import TrainerProfile, ensure_onboarding_children
from .onboarding_meta import ONBOARDING_STEPS, TAB_LABELS
from .profile_display import (
    non_empty_additional_qualifications,
    non_empty_specialisms,
    quick_qualification_labels,
    training_location_items,
    visible_price_tiers,
)

STEP_COUNT = 6


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
        public_profile_url = request.build_absolute_uri(
            reverse('pages:trainer_profile', kwargs={'profile_slug': profile.slug})
        )

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


@login_required
def onboarding_step(request, step: int, onboarding_edit: bool = False):
    if not 1 <= step <= STEP_COUNT:
        raise Http404
    step_idx = step - 1
    profile = _get_profile(request.user)

    if onboarding_edit and not profile.completed_at:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        if not onboarding_edit:
            return redirect('pages:onboarding_complete')

    if not onboarding_edit and step_idx > profile.onboarding_step:
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
        'areas_for_js': AREAS,
        'max_reachable_step': max_reachable_step,
        'onboarding_edit': onboarding_edit,
    }

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
                if onboarding_edit:
                    return redirect('pages:onboarding_step_edit', step=step)
                return redirect('pages:onboarding_step', step=step)
            if step_idx == STEP_COUNT - 1:
                if onboarding_edit:
                    messages.success(request, 'Your page has been updated.')
                    return redirect('pages:trainer_profile', profile_slug=profile.slug)
                return redirect('pages:onboarding_complete')
            if onboarding_edit:
                return redirect('pages:onboarding_step_edit', step=step + 1)
            return redirect('pages:onboarding_step', step=step + 1)
        messages.error(request, 'Please correct the errors below.')
        context.update(errors)
    else:
        _load_step_get_forms(context, profile, step_idx)

    return render(request, 'pages/onboarding.html', context)


@login_required
def onboarding_complete(request):
    profile = _get_profile(request.user)
    if not profile.completed_at:
        return redirect('pages:onboarding')
    return render(request, 'pages/onboarding_complete.html', {'profile': profile})


def trainer_profile_id_redirect(request, profile_id: int):
    profile = get_object_or_404(TrainerProfile, pk=profile_id)
    return redirect(
        'pages:trainer_profile',
        profile_slug=profile.slug,
        permanent=True,
    )


def trainer_public_profile(request, profile_slug: str):
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('user').prefetch_related(
            'additional_qualifications',
            'specialisms',
            'price_tiers',
            'gallery_photos',
        ),
        slug__iexact=profile_slug,
    )
    is_owner = request.user.is_authenticated and request.user.pk == profile.user_id
    if not is_owner:
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
