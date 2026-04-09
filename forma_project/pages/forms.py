"""
Onboarding forms for PT profile setup (6 steps). Widgets use `.forma-input` (see static_src/css/input.css).

View wiring (after user has a TrainerProfile and `ensure_onboarding_children(profile)` has run):
  Step 1: OnboardingStep1Form
  Step 2: OnboardingStep2QuickForm + TrainerAdditionalQualificationFormSet
  Step 3: TrainerSpecialismFormSet
  Step 4: OnboardingStep4Form (saves training_locations + other_areas JSON on save())
  Step 5: OnboardingStep5MetaForm + TrainerPriceTierFormSet
  Step 6: OnboardingStep6InstagramForm + TrainerGalleryPhotoFormSet

Constants: AREAS, AREA_NAMES, QUICK_QUALIFICATION_CHOICES, TRAINING_LOCATION_CHOICES (re-exported from models for choices).
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    QUICK_QUALIFICATION_CHOICES,
    TRAINING_LOCATION_CHOICES,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
)

FORMA_INPUT_CLASS = 'forma-input'


def _forma_attrs(extra=None):
    attrs = {'class': FORMA_INPUT_CLASS}
    if extra:
        attrs.update(extra)
    return attrs


# ── London / SW areas (from onboarding mock) ────────────────────────────────
AREAS = [
    {'name': 'Balham', 'postcode': 'SW12'},
    {'name': 'Barnes', 'postcode': 'SW13'},
    {'name': 'Battersea', 'postcode': 'SW11'},
    {'name': 'Bermondsey', 'postcode': 'SE1'},
    {'name': 'Brixton', 'postcode': 'SW2'},
    {'name': 'Camberwell', 'postcode': 'SE5'},
    {'name': 'Chelsea', 'postcode': 'SW3'},
    {'name': 'Clapham', 'postcode': 'SW4'},
    {'name': 'Dulwich', 'postcode': 'SE21'},
    {'name': 'East Sheen', 'postcode': 'SW14'},
    {'name': 'Elephant & Castle', 'postcode': 'SE1'},
    {'name': 'Fulham', 'postcode': 'SW6'},
    {'name': 'Herne Hill', 'postcode': 'SE24'},
    {'name': 'Kennington', 'postcode': 'SE11'},
    {'name': 'Kew', 'postcode': 'TW9'},
    {'name': 'Mortlake', 'postcode': 'SW14'},
    {'name': 'New Malden', 'postcode': 'KT3'},
    {'name': 'Oval', 'postcode': 'SE11'},
    {'name': 'Peckham', 'postcode': 'SE15'},
    {'name': 'Putney', 'postcode': 'SW15'},
    {'name': 'Richmond', 'postcode': 'TW10'},
    {'name': 'Roehampton', 'postcode': 'SW15'},
    {'name': 'South Wimbledon', 'postcode': 'SW19'},
    {'name': 'Stockwell', 'postcode': 'SW9'},
    {'name': 'Streatham', 'postcode': 'SW16'},
    {'name': 'Surbiton', 'postcode': 'KT6'},
    {'name': 'Tooting', 'postcode': 'SW17'},
    {'name': 'Tulse Hill', 'postcode': 'SE27'},
    {'name': 'Vauxhall', 'postcode': 'SE11'},
    {'name': 'Wandsworth', 'postcode': 'SW18'},
    {'name': 'Wimbledon', 'postcode': 'SW19'},
]

AREA_NAMES = [a['name'] for a in AREAS]
AREA_NAME_SET = frozenset(AREA_NAMES)
POSTCODE_CHOICES = sorted({a['postcode'] for a in AREAS})
PRIMARY_AREA_CHOICES = [('', 'Select your primary area')] + [(n, n) for n in AREA_NAMES]
POSTCODE_SELECT_CHOICES = [('', 'Select postcode')] + [(p, p) for p in POSTCODE_CHOICES]


def other_area_choices(exclude_name=None):
    names = [n for n in AREA_NAMES if n != exclude_name]
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
            'detail': forms.TextInput(attrs=_forma_attrs({'placeholder': 'Detail or year'})),
        }


TrainerAdditionalQualificationFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerAdditionalQualification,
    form=AdditionalQualificationForm,
    extra=0,
    can_delete=False,
    max_num=4,
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
        fields = ('primary_area', 'postcode_district')
        widgets = {
            'primary_area': forms.Select(attrs=_forma_attrs()),
            'postcode_district': forms.Select(attrs=_forma_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['primary_area'].choices = PRIMARY_AREA_CHOICES
        self.fields['postcode_district'].choices = POSTCODE_SELECT_CHOICES
        exclude = (self.instance.primary_area or None) if self.instance.pk else None
        self.fields['other_areas'].choices = other_area_choices(exclude)

        if self.instance.pk:
            self.fields['training_locations'].initial = self.instance.training_locations or []
            self.fields['other_areas'].initial = self.instance.other_areas or []

    def clean_primary_area(self):
        name = self.cleaned_data.get('primary_area') or ''
        name = name.strip()
        if name and name not in AREA_NAME_SET:
            raise ValidationError('Select a valid primary area.')
        return name

    def clean_postcode_district(self):
        pc = self.cleaned_data.get('postcode_district') or ''
        pc = pc.strip()
        if pc and pc not in POSTCODE_CHOICES:
            raise ValidationError('Select a valid postcode district.')
        return pc

    def clean_other_areas(self):
        selected = self.cleaned_data.get('other_areas') or []
        for n in selected:
            if n not in AREA_NAME_SET:
                raise ValidationError('Invalid area selected.')
        return list(selected)

    def clean(self):
        data = super().clean()
        primary = (data.get('primary_area') or '').strip()
        others = data.get('other_areas') or []
        if primary and primary in others:
            raise ValidationError('Primary area cannot also be listed under other areas.')
        if primary:
            allowed = {a['postcode'] for a in AREAS if a['name'] == primary}
            pc = (data.get('postcode_district') or '').strip()
            if pc and allowed and pc not in allowed:
                raise ValidationError(
                    {'postcode_district': 'Pick a postcode that matches your primary area.'}
                )
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
        fields = ('instagram_handle',)
        widgets = {
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
