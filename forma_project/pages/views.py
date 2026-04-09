from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
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
def onboarding_redirect(request):
    profile = _get_profile(request.user)
    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:onboarding_complete')
    return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)


@login_required
def onboarding_step(request, step: int):
    if not 1 <= step <= STEP_COUNT:
        raise Http404
    step_idx = step - 1
    profile = _get_profile(request.user)

    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:onboarding_complete')

    if step_idx > profile.onboarding_step:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

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
        'max_reachable_step': profile.onboarding_step + 1,
    }

    if request.method == 'POST':
        advance = not request.POST.get('save_draft')
        ok, errors = _process_step_post(request, profile, step_idx, advance=advance)
        if ok:
            if not advance:
                messages.success(request, 'Draft saved.')
                return redirect('pages:onboarding_step', step=step)
            if step_idx == STEP_COUNT - 1:
                return redirect('pages:onboarding_complete')
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


def _process_step_post(
    request,
    profile: TrainerProfile,
    step_idx: int,
    *,
    advance: bool = True,
) -> tuple[bool, dict]:
    if step_idx == 0:
        form = OnboardingStep1Form(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            if advance:
                _advance_profile(profile, step_idx)
            return True, {}
        return False, {'form': form}

    if step_idx == 1:
        quick = OnboardingStep2QuickForm(request.POST)
        fs = TrainerAdditionalQualificationFormSet(request.POST, instance=profile)
        if quick.is_valid() and fs.is_valid():
            profile.quick_qualifications = list(quick.cleaned_data.get('quick_qualifications') or [])
            profile.save(update_fields=['quick_qualifications'])
            fs.save()
            if advance:
                _advance_profile(profile, step_idx)
            return True, {}
        return False, {'quick_form': quick, 'formset': fs}

    if step_idx == 2:
        fs = TrainerSpecialismFormSet(request.POST, instance=profile)
        if fs.is_valid():
            fs.save()
            if advance:
                _advance_profile(profile, step_idx)
            return True, {}
        return False, {'formset': fs}

    if step_idx == 3:
        form = OnboardingStep4Form(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            if advance:
                _advance_profile(profile, step_idx)
            return True, {}
        return False, {'form': form}

    if step_idx == 4:
        meta = OnboardingStep5MetaForm(request.POST, instance=profile)
        pfs = TrainerPriceTierFormSet(request.POST, instance=profile)
        if meta.is_valid() and pfs.is_valid():
            meta.save()
            pfs.save()
            if advance:
                _advance_profile(profile, step_idx)
            return True, {}
        return False, {'meta_form': meta, 'formset': pfs}

    if step_idx == 5:
        ig = OnboardingStep6InstagramForm(request.POST, instance=profile)
        gfs = TrainerGalleryPhotoFormSet(request.POST, request.FILES, instance=profile)
        if ig.is_valid() and gfs.is_valid():
            ig.save()
            gfs.save()
            if advance:
                _advance_profile(profile, step_idx)
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
