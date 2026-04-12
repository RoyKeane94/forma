"""
Onboarding forms for PT profile setup (7 steps). Widgets use `.forma-input` (see static_src/css/input.css).

View wiring (after user has a TrainerProfile and `ensure_onboarding_children(profile)` has run):
  Step 1: OnboardingStep1Form
  Step 2: OnboardingStep2QuickForm + TrainerAdditionalQualificationFormSet (up to 10 rows)
  Step 3: TrainerSpecialismFormSet
  Step 4: OnboardingStep4Form (saves training_locations + other_areas JSON on save())
  Step 5: OnboardingStep5MetaForm + TrainerPriceTierFormSet
  Step 6: OnboardingStep6InstagramForm (intro video, show toggle, Instagram) + TrainerGalleryPhotoFormSet
  Step 7: OnboardingStep7ReviewsForm → TrainerProfile.client_reviews (max 3)

Constants: QUICK_QUALIFICATION_CHOICES, TRAINING_LOCATION_CHOICES (from models).
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    QUICK_QUALIFICATION_CHOICES,
    TRAINING_LOCATION_CHOICES,
    PrimaryArea,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
)
from .profile_display import non_empty_specialisms

FORMA_INPUT_CLASS = 'forma-input'


def _forma_attrs(extra=None):
    attrs = {'class': FORMA_INPUT_CLASS}
    if extra:
        attrs.update(extra)
    return attrs


def _primary_area_queryset():
    return PrimaryArea.objects.select_related('district').order_by('name')


def other_area_choices():
    """All catalogue names; primary is de-duplicated in clean() / save, not excluded from the UI."""
    names = list(_primary_area_queryset().values_list('name', flat=True))
    return [(n, n) for n in names]


# ── Step 1 ──────────────────────────────────────────────────────────────────


class OnboardingStep1Form(forms.ModelForm):
    class Meta:
        model = TrainerProfile
        fields = ('first_name', 'last_name', 'tagline', 'bio', 'portrait')
        widgets = {
            'first_name': forms.TextInput(attrs=_forma_attrs({'placeholder': 'Maya', 'autocomplete': 'given-name'})),
            'last_name': forms.TextInput(attrs=_forma_attrs({'placeholder': 'Torres', 'autocomplete': 'family-name'})),
            'tagline': forms.TextInput(
                attrs=_forma_attrs(
                    {
                        'placeholder': 'Strength training for people who are done doing things half-heartedly',
                        'maxlength': '80',
                    }
                )
            ),
            'bio': forms.Textarea(
                attrs=_forma_attrs(
                    {
                        'rows': 7,
                        'placeholder': "I've been training clients in South London for seven years…",
                    }
                )
            ),
            'portrait': forms.ClearableFileInput(
                attrs={
                    'class': FORMA_INPUT_CLASS,
                    'accept': 'image/*',
                }
            ),
        }

    def clean_tagline(self):
        data = self.cleaned_data['tagline'].strip()
        if len(data) > 80:
            raise ValidationError('Tagline must be 80 characters or fewer.')
        return data


# ── Step 2 ──────────────────────────────────────────────────────────────────


class OnboardingStep2QuickForm(forms.Form):
    """Quick-add presets; persisted to TrainerProfile.quick_qualifications."""

    quick_qualifications = forms.MultipleChoiceField(
        label='Quick add',
        choices=QUICK_QUALIFICATION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class AdditionalQualificationForm(forms.ModelForm):
    class Meta:
        model = TrainerAdditionalQualification
        fields = ('name', 'detail')
        widgets = {
            'name': forms.TextInput(attrs=_forma_attrs({'placeholder': 'Qualification name'})),
            'detail': forms.TextInput(
                attrs=_forma_attrs({'placeholder': 'Tell clients what this qualifies you for'})
            ),
        }


TrainerAdditionalQualificationFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerAdditionalQualification,
    form=AdditionalQualificationForm,
    extra=0,
    can_delete=False,
    max_num=10,
    validate_max=True,
)


# ── Step 3 ──────────────────────────────────────────────────────────────────


class TrainerSpecialismForm(forms.ModelForm):
    class Meta:
        model = TrainerSpecialism
        fields = ('title',)
        widgets = {
            'title': forms.TextInput(
                attrs=_forma_attrs({'placeholder': 'e.g. Strength Training'}),
            ),
        }


TrainerSpecialismFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerSpecialism,
    form=TrainerSpecialismForm,
    extra=0,
    can_delete=False,
    max_num=4,
    validate_max=True,
)


# ── Step 4 ──────────────────────────────────────────────────────────────────


class OnboardingStep4Form(forms.ModelForm):
    training_locations = forms.MultipleChoiceField(
        label='Where do you train?',
        choices=TRAINING_LOCATION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    other_areas = forms.MultipleChoiceField(
        label='Other areas covered',
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = TrainerProfile
        fields = ('primary_area',)
        widgets = {
            'primary_area': forms.Select(attrs=_forma_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pa = self.fields['primary_area']
        pa.queryset = _primary_area_queryset()
        pa.empty_label = 'Select your primary area'
        pa.required = False
        self.fields['other_areas'].choices = other_area_choices()

        if self.instance.pk:
            self.fields['training_locations'].initial = self.instance.training_locations or []
            self.fields['other_areas'].initial = self.instance.other_areas or []

    def clean_other_areas(self):
        selected = self.cleaned_data.get('other_areas') or []
        valid = frozenset(_primary_area_queryset().values_list('name', flat=True))
        for n in selected:
            if n not in valid:
                raise ValidationError('Invalid area selected.')
        return list(selected)

    def clean(self):
        data = super().clean()
        primary = data.get('primary_area')
        others = list(data.get('other_areas') or [])
        if primary is not None:
            others = [n for n in others if n != primary.name]
        data['other_areas'] = others
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.training_locations = self.cleaned_data.get('training_locations') or []
        instance.other_areas = self.cleaned_data.get('other_areas') or []
        if commit:
            instance.save()
        return instance


# ── Step 5 ──────────────────────────────────────────────────────────────────


class TrainerPriceTierForm(forms.ModelForm):
    class Meta:
        model = TrainerPriceTier
        fields = ('label', 'unit_note', 'price')
        widgets = {
            'label': forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. Single session'})),
            'unit_note': forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. per session'})),
            'price': forms.NumberInput(
                attrs=_forma_attrs({'placeholder': '65', 'min': '0', 'step': '0.01'}),
            ),
        }


TrainerPriceTierFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerPriceTier,
    form=TrainerPriceTierForm,
    extra=0,
    can_delete=False,
    max_num=4,
    validate_max=True,
)


class OnboardingStep5MetaForm(forms.ModelForm):
    """Free consultation flag only; pricing rows come from the formset."""

    class Meta:
        model = TrainerProfile
        fields = ('free_consultation',)


# ── Step 6 ──────────────────────────────────────────────────────────────────


class TrainerGalleryPhotoForm(forms.ModelForm):
    class Meta:
        model = TrainerGalleryPhoto
        fields = ('image',)
        widgets = {
            'image': forms.ClearableFileInput(
                attrs={
                    'class': FORMA_INPUT_CLASS,
                    'accept': 'image/*',
                }
            ),
        }


TrainerGalleryPhotoFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerGalleryPhoto,
    form=TrainerGalleryPhotoForm,
    extra=0,
    can_delete=False,
    max_num=6,
    validate_max=True,
)


class OnboardingStep6InstagramForm(forms.ModelForm):
    class Meta:
        model = TrainerProfile
        fields = ('intro_video', 'show_intro_video', 'instagram_handle')
        widgets = {
            'intro_video': forms.ClearableFileInput(
                attrs={
                    'class': FORMA_INPUT_CLASS,
                    'accept': 'video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v',
                }
            ),
            'instagram_handle': forms.TextInput(
                attrs={
                    **_forma_attrs(
                        {
                            'placeholder': 'yourusername',
                            'autocomplete': 'off',
                        }
                    ),
                    'class': f'{FORMA_INPUT_CLASS} pl-7',
                }
            ),
        }

    def clean_instagram_handle(self):
        h = (self.cleaned_data.get('instagram_handle') or '').strip().lstrip('@')
        if len(h) > 64:
            raise ValidationError('Handle is too long.')
        return h


MAX_ONBOARDING_REVIEWS = 3

_REVIEW_RATING_CHOICES = [('', '—')] + [(str(n), '★' * n) for n in range(1, 6)]


def client_reviews_form_initial(profile: TrainerProfile) -> dict:
    init = {}
    rows = profile.client_reviews or []
    for i in range(MAX_ONBOARDING_REVIEWS):
        row = rows[i] if i < len(rows) else {}
        if not isinstance(row, dict):
            row = {}
        init[f'review_{i}_name'] = row.get('name', '')
        init[f'review_{i}_quote'] = row.get('quote', '')
        r = row.get('rating')
        if isinstance(r, (int, float)) and 1 <= int(r) <= 5:
            init[f'review_{i}_rating'] = str(int(r))
        else:
            init[f'review_{i}_rating'] = ''
        init[f'review_{i}_confirmed'] = bool(row.get('confirmed'))
        init[f'review_{i}_focus'] = (row.get('focus') or '').strip()
    return init


class OnboardingStep7ReviewsForm(forms.Form):
    """Up to three reviews (name, quote, 1–5 stars, confirmation, optional focus); persisted to TrainerProfile.client_reviews."""

    review_0_name = forms.CharField(
        label='Reviewer name',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. Jamie T.'})),
    )
    review_0_quote = forms.CharField(
        label='What they said',
        max_length=600,
        required=False,
        widget=forms.Textarea(attrs=_forma_attrs({'rows': 3, 'placeholder': 'Short testimonial…'})),
    )
    review_0_rating = forms.ChoiceField(
        label='Star rating',
        choices=_REVIEW_RATING_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={'class': 'forma-review-star-radios'}),
    )
    review_0_confirmed = forms.BooleanField(required=False)
    review_0_focus = forms.ChoiceField(
        label='Focus area',
        choices=[('', '—')],
        required=False,
        widget=forms.Select(attrs=_forma_attrs()),
    )
    review_1_name = forms.CharField(
        label='Reviewer name',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. Sam K.'})),
    )
    review_1_quote = forms.CharField(
        label='What they said',
        max_length=600,
        required=False,
        widget=forms.Textarea(attrs=_forma_attrs({'rows': 3, 'placeholder': 'Short testimonial…'})),
    )
    review_1_rating = forms.ChoiceField(
        label='Star rating',
        choices=_REVIEW_RATING_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={'class': 'forma-review-star-radios'}),
    )
    review_1_confirmed = forms.BooleanField(required=False)
    review_1_focus = forms.ChoiceField(
        label='Focus area',
        choices=[('', '—')],
        required=False,
        widget=forms.Select(attrs=_forma_attrs()),
    )
    review_2_name = forms.CharField(
        label='Reviewer name',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. Priya N.'})),
    )
    review_2_quote = forms.CharField(
        label='What they said',
        max_length=600,
        required=False,
        widget=forms.Textarea(attrs=_forma_attrs({'rows': 3, 'placeholder': 'Short testimonial…'})),
    )
    review_2_rating = forms.ChoiceField(
        label='Star rating',
        choices=_REVIEW_RATING_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={'class': 'forma-review-star-radios'}),
    )
    review_2_confirmed = forms.BooleanField(required=False)
    review_2_focus = forms.ChoiceField(
        label='Focus area',
        choices=[('', '—')],
        required=False,
        widget=forms.Select(attrs=_forma_attrs()),
    )

    def __init__(self, *args, profile=None, **kwargs):
        self._profile = profile
        super().__init__(*args, **kwargs)
        base_titles = non_empty_specialisms(profile) if profile is not None else []
        for i in range(MAX_ONBOARDING_REVIEWS):
            slot_titles = list(dict.fromkeys(base_titles))
            v = (self.initial.get(f'review_{i}_focus') or '').strip()
            if v and v not in slot_titles:
                slot_titles.append(v)
            if slot_titles:
                focus_choices = [('', 'Choose one of your specialisms')] + [(t, t) for t in slot_titles]
            else:
                focus_choices = [
                    (
                        '',
                        'Add specialisms in step 3 to link a review to a focus area',
                    )
                ]
            self.fields[f'review_{i}_focus'].choices = focus_choices

    def clean(self):
        data = super().clean()
        out = []
        profile = getattr(self, '_profile', None)
        spec_titles = frozenset(non_empty_specialisms(profile)) if profile is not None else frozenset()
        prev_rows = (profile.client_reviews or []) if profile is not None else []
        for i in range(MAX_ONBOARDING_REVIEWS):
            n = (data.get(f'review_{i}_name') or '').strip()
            q = (data.get(f'review_{i}_quote') or '').strip()
            rat_raw = (data.get(f'review_{i}_rating') or '').strip()
            confirmed = bool(data.get(f'review_{i}_confirmed'))
            fo = (data.get(f'review_{i}_focus') or '').strip()
            prev_f = ''
            if i < len(prev_rows) and isinstance(prev_rows[i], dict):
                prev_f = (prev_rows[i].get('focus') or '').strip()
            allowed_focus = set(spec_titles)
            if prev_f:
                allowed_focus.add(prev_f)

            if not n and not q and not rat_raw and not confirmed and not fo:
                continue

            if not n and not q:
                if rat_raw or confirmed or fo:
                    self.add_error(
                        f'review_{i}_name',
                        'Add reviewer name and quote, or clear this slot.',
                    )
                continue

            if n and not q:
                self.add_error(f'review_{i}_quote', 'Add a quote for this review or clear the name.')
            elif q and not n:
                self.add_error(f'review_{i}_name', 'Add a reviewer name or clear the quote.')
            elif n and q:
                rating_val = int(rat_raw) if rat_raw.isdigit() and 1 <= int(rat_raw) <= 5 else None
                if rating_val is None:
                    self.add_error(f'review_{i}_rating', 'Choose a star rating from 1 to 5.')
                if not confirmed:
                    self.add_error(
                        f'review_{i}_confirmed',
                        'Tick to confirm that this is a true review.',
                    )
                if spec_titles and fo not in allowed_focus:
                    self.add_error(
                        f'review_{i}_focus',
                        'Choose which of your specialisms this review relates to.',
                    )
                if rating_val is not None and confirmed and (not spec_titles or fo in allowed_focus):
                    row = {
                        'name': n,
                        'quote': q,
                        'rating': rating_val,
                        'confirmed': True,
                    }
                    if fo:
                        row['focus'] = fo
                    out.append(row)
        self._reviews_json = out
        return data

    def save_to_profile(self, profile: TrainerProfile) -> None:
        profile.client_reviews = getattr(self, '_reviews_json', [])
        profile.save(update_fields=['client_reviews'])


class StaffTrainerCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'given-name'})))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'family-name'})))
