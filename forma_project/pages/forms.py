"""
Onboarding forms for PT profile setup (7 steps). Widgets use `.forma-input` (see static_src/css/input.css).

View wiring (call `ensure_onboarding_children(profile)` before step 0 GET/POST so child rows exist):
  Step 1: OnboardingStep1Form + TrainerWhoIWorkWithFormSet (identity, tagline, bio, who I work with rows, contact, portrait)
  Step 2: OnboardingStep2QuickForm + TrainerAdditionalQualificationFormSet (up to 10 rows)
  Step 3: TrainerSpecialismFormSet (up to four rows: title + optional brief description)
  Step 4: OnboardingStep4Form (saves training_locations + other_areas JSON: catalogue names and/or {name, outward})
  Step 5: OnboardingStep5MetaForm + TrainerPriceTierFormSet (up to 10 tiers + one blank row to add more)
  Step 6: OnboardingStep6InstagramForm (intro video, show toggle, Instagram) + TrainerGalleryPhotoFormSet
  Step 7: OnboardingStep7ReviewsForm → TrainerProfile.client_reviews (max 3) + featured_review_slot

Constants: QUICK_QUALIFICATION_CHOICES, TRAINING_LOCATION_CHOICES (from models).
"""

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet

from .models import (
    QUICK_QUALIFICATION_CHOICES,
    TRAINING_LOCATION_CHOICES,
    PrimaryArea,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
    TrainerWhoIWorkWithItem,
)
from .profile_display import non_empty_specialisms

FORMA_INPUT_CLASS = 'forma-input'

# Step 5 — example copy for the first four pricing rows (placeholders); rows 5+ use generics in the form.
PRICE_TIER_PLACEHOLDER_ROWS = [
    ('Single session', 'per session', '65'),
    ('Multiple sessions', '5 sessions', '300'),
    ('Single group session', 'per session', '50'),
    ('Multiple group sessions', '10 sessions', '450'),
]
PRICE_TIER_MAX_NUM = 10

WHO_I_WORK_WITH_MAX_NUM = 8


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


_UK_POSTCODE_OUTWARD_RE = re.compile(r'^[A-Z]{1,2}\d[A-Z0-9]{0,2}$')


def validate_uk_postcode_outward(value: str) -> str:
    """Accept UK postcode outward part only (e.g. TW10, W4, SW1A), not a full postcode."""
    raw_in = (value or '').strip()
    if not raw_in:
        raise ValidationError('Enter the postcode district (for example TW10 or W4).')
    parts = raw_in.upper().split()
    if len(parts) > 1:
        raise ValidationError('Enter only the postcode district (e.g. TW10), not a full postcode.')
    code = parts[0]
    if len(code) > 4:
        raise ValidationError('That does not look like a valid postcode district.')
    if not _UK_POSTCODE_OUTWARD_RE.fullmatch(code):
        raise ValidationError('Enter a valid UK postcode district (for example TW10 or W4).')
    return code


def _split_stored_other_areas(raw: list, catalogue_names: frozenset[str]) -> tuple[list[str], list[dict]]:
    """Split JSON `other_areas` into catalogue names and {name, outward} custom rows."""
    cat: list[str] = []
    custom: list[dict] = []
    for x in raw or []:
        if isinstance(x, dict):
            name = (x.get('name') or '').strip()
            outward = (x.get('outward') or '').strip().upper()
            if not name:
                continue
            custom.append({'name': name, 'outward': outward})
        elif isinstance(x, str) and (x or '').strip():
            s = x.strip()
            if s in catalogue_names:
                cat.append(s)
            else:
                custom.append({'name': s, 'outward': ''})
    return cat, custom


# ── Step 1 ──────────────────────────────────────────────────────────────────


class OnboardingStep1Form(forms.ModelForm):
    class Meta:
        model = TrainerProfile
        fields = (
            'first_name',
            'last_name',
            'tagline',
            'bio',
            'contact_email',
            'contact_phone',
            'contact_phone_preference',
            'portrait',
        )
        labels = {
            'contact_email': 'Contact email',
            'contact_phone': 'Contact phone',
            'contact_phone_preference': 'Preferred contact method for this number',
        }
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
            'contact_email': forms.EmailInput(
                attrs=_forma_attrs(
                    {
                        'placeholder': 'you@example.com',
                        'autocomplete': 'email',
                        'inputmode': 'email',
                    }
                )
            ),
            'contact_phone': forms.TextInput(
                attrs=_forma_attrs(
                    {
                        'placeholder': '+44 7700 900000',
                        'autocomplete': 'tel',
                        'inputmode': 'tel',
                    }
                )
            ),
            'contact_phone_preference': forms.RadioSelect(),
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

    def clean_contact_phone(self):
        return (self.cleaned_data.get('contact_phone') or '').strip()

    def clean(self):
        data = super().clean()
        phone = (data.get('contact_phone') or '').strip()
        pref = (data.get('contact_phone_preference') or '').strip()
        if phone and not pref:
            self.add_error(
                'contact_phone_preference',
                'Choose how you prefer to be reached on this number (call, WhatsApp, or text).',
            )
        if pref and not phone:
            self.add_error('contact_phone', 'Enter a phone number, or clear the preferred contact method.')
        return data


class TrainerWhoIWorkWithItemForm(forms.ModelForm):
    class Meta:
        model = TrainerWhoIWorkWithItem
        fields = ('title', 'description')
        widgets = {
            'title': forms.TextInput(
                attrs=_forma_attrs({'placeholder': 'e.g. Complete beginners'}),
            ),
            'description': forms.Textarea(
                attrs=_forma_attrs(
                    {
                        'rows': 3,
                        'placeholder': 'Who they are and how you help them…',
                    }
                )
            ),
        }


class TrainerWhoIWorkWithInlineFormSet(BaseInlineFormSet):
    """Up to WHO_I_WORK_WITH_MAX_NUM rows; one extra blank row to add another."""

    def get_queryset(self):
        return super().get_queryset().filter(order__lte=WHO_I_WORK_WITH_MAX_NUM).order_by('order')

    def save_new(self, form, commit=True):
        obj = form.save(commit=False)
        setattr(obj, self.fk.name, self.instance)
        next_order = (
            self.model.objects.filter(**{self.fk.name: self.instance}).aggregate(m=Max('order'))['m']
            or 0
        ) + 1
        if next_order > WHO_I_WORK_WITH_MAX_NUM:
            raise ValidationError(f'You can add at most {WHO_I_WORK_WITH_MAX_NUM} client types.')
        obj.order = next_order
        if commit:
            obj.save()
            if hasattr(form, 'save_m2m'):
                form.save_m2m()
        return obj


TrainerWhoIWorkWithFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerWhoIWorkWithItem,
    form=TrainerWhoIWorkWithItemForm,
    formset=TrainerWhoIWorkWithInlineFormSet,
    extra=1,
    can_delete=False,
    max_num=WHO_I_WORK_WITH_MAX_NUM,
    validate_max=True,
)


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
        fields = ('title', 'description')
        widgets = {
            'title': forms.TextInput(
                attrs=_forma_attrs({'placeholder': 'e.g. Strength Training'}),
            ),
            'description': forms.Textarea(
                attrs=_forma_attrs(
                    {
                        'rows': 2,
                        'placeholder': 'Optional — one sentence on what this means for clients',
                    }
                )
            ),
        }

    def clean_description(self):
        return (self.cleaned_data.get('description') or '').strip()


class TrainerSpecialismInlineFormSet(BaseInlineFormSet):
    """Cap at four rows even if legacy data created orders 5–10."""

    def get_queryset(self):
        return super().get_queryset().filter(order__lte=4)


TrainerSpecialismFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerSpecialism,
    form=TrainerSpecialismForm,
    formset=TrainerSpecialismInlineFormSet,
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
    other_areas_custom = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'data-custom-other-areas': '1'}),
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
            valid = frozenset(_primary_area_queryset().values_list('name', flat=True))
            cat_init, custom_init = _split_stored_other_areas(
                list(self.instance.other_areas or []),
                valid,
            )
            self.fields['other_areas'].initial = cat_init
            self.fields['other_areas_custom'].initial = json.dumps(custom_init)

    def clean_other_areas(self):
        selected = self.cleaned_data.get('other_areas') or []
        valid = frozenset(_primary_area_queryset().values_list('name', flat=True))
        for n in selected:
            if n not in valid:
                raise ValidationError('Invalid area selected.')
        return list(selected)

    def _parse_custom_other_areas_json(self) -> list[dict] | None:
        raw = (self.data.get('other_areas_custom') if self.data is not None else '') or ''
        if len(raw) > 10000:
            self.add_error('other_areas_custom', 'Too many custom areas.')
            return None
        try:
            payload = json.loads(raw.strip() or '[]')
        except json.JSONDecodeError:
            self.add_error('other_areas_custom', 'Could not read the extra areas you added. Please try again.')
            return None
        if not isinstance(payload, list):
            self.add_error('other_areas_custom', 'Invalid extra areas data.')
            return None
        if len(payload) > 20:
            self.add_error('other_areas_custom', 'You can add at most 20 areas that are not in the list.')
            return None

        out: list[dict] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = (item.get('name') or '').strip()
            outward_raw = (item.get('outward') or '').strip()
            if not name and not outward_raw:
                continue
            if len(name) > 128:
                self.add_error('other_areas_custom', 'Each area name must be 128 characters or fewer.')
                return None
            if not name:
                self.add_error('other_areas_custom', 'Give each extra area a name.')
                return None
            try:
                outward = validate_uk_postcode_outward(outward_raw)
            except ValidationError as e:
                self.add_error('other_areas_custom', e)
                return None
            out.append({'name': name, 'outward': outward})

        seen: set[str] = set()
        for row in out:
            k = row['name'].casefold()
            if k in seen:
                self.add_error('other_areas_custom', 'You have the same extra area more than once.')
                return None
            seen.add(k)
        return out

    def clean(self):
        data = super().clean()
        catalogue = list(self.cleaned_data.get('other_areas') or [])
        custom_rows = self._parse_custom_other_areas_json()
        if custom_rows is None:
            return data

        cat_cf = {n.casefold() for n in catalogue}
        for row in custom_rows:
            if row['name'].casefold() in cat_cf:
                self.add_error(
                    'other_areas_custom',
                    f'“{row["name"]}” is already selected above; remove it from extra areas or untick it.',
                )
                return data

        primary = data.get('primary_area')
        primary_name_cf = (primary.name.casefold() if primary is not None else '') or ''
        if primary_name_cf:
            catalogue = [n for n in catalogue if n.casefold() != primary_name_cf]
            custom_rows = [r for r in custom_rows if r['name'].casefold() != primary_name_cf]

        merged: list = [*catalogue, *custom_rows]
        data['other_areas'] = merged
        self.cleaned_data['other_areas'] = merged
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.training_locations = self.cleaned_data.get('training_locations') or []
        instance.other_areas = self.cleaned_data.get('other_areas') or []
        if commit:
            instance.save()
        return instance


# ── Step 5 ──────────────────────────────────────────────────────────────────


class TierCaptionRadioSelect(forms.RadioSelect):
    """Radio option label wrapped in .js-tier-radio-caption for live caption updates."""

    option_template_name = 'pages/widgets/tier_radio_option.html'


def price_tier_row_captions_for_meta_form(formset) -> list[str]:
    """One caption per form row for “most popular” radios (label, else unit note, else row number)."""
    out: list[str] = []
    for i, form in enumerate(formset.forms):
        row_ref = f'{i + 1:02d}'
        raw = ''
        data = getattr(form, 'data', None)
        if data is not None:
            raw = (data.get(form.add_prefix('label')) or '').strip()
        if not raw:
            raw = (getattr(form.instance, 'label', None) or '').strip()
        if not raw and data is not None:
            raw = (data.get(form.add_prefix('unit_note')) or '').strip()
        if not raw:
            raw = (getattr(form.instance, 'unit_note', None) or '').strip()
        if not raw:
            display = f'Row {row_ref}'
        elif len(raw) > 56:
            display = raw[:55] + '…'
        else:
            display = raw
        out.append(display)
    return out


class TrainerPriceTierForm(forms.ModelForm):
    class Meta:
        model = TrainerPriceTier
        fields = ('label', 'unit_note', 'price')
        widgets = {
            'label': forms.TextInput(attrs=_forma_attrs()),
            'unit_note': forms.TextInput(attrs=_forma_attrs()),
            'price': forms.NumberInput(attrs=_forma_attrs({'min': '0', 'step': '0.01'})),
        }

    def _placeholder_row_index(self) -> int:
        if getattr(self.instance, 'pk', None):
            return int(self.instance.order)
        if self.prefix:
            tail = self.prefix.rsplit('-', 1)[-1]
            if tail.isdigit():
                return int(tail) + 1
        return 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        row = self._placeholder_row_index()
        presets = PRICE_TIER_PLACEHOLDER_ROWS
        if 1 <= row <= len(presets):
            label_p, unit_p, price_p = presets[row - 1]
        else:
            label_p, unit_p, price_p = (
                'e.g. Package or bundle',
                'e.g. per month',
                '',
            )
        self.fields['label'].widget.attrs['placeholder'] = label_p
        self.fields['unit_note'].widget.attrs['placeholder'] = unit_p
        if price_p:
            self.fields['price'].widget.attrs['placeholder'] = price_p
        else:
            self.fields['price'].widget.attrs.pop('placeholder', None)


class TrainerPriceTierInlineFormSet(BaseInlineFormSet):
    """Up to PRICE_TIER_MAX_NUM saved rows; one extra empty form to add another tier."""

    def get_queryset(self):
        return super().get_queryset().filter(order__lte=PRICE_TIER_MAX_NUM).order_by('order')

    def save_new(self, form, commit=True):
        obj = form.save(commit=False)
        setattr(obj, self.fk.name, self.instance)
        next_order = (
            self.model.objects.filter(**{self.fk.name: self.instance}).aggregate(m=Max('order'))['m']
            or 0
        ) + 1
        if next_order > PRICE_TIER_MAX_NUM:
            raise ValidationError(f'You can add at most {PRICE_TIER_MAX_NUM} price options.')
        obj.order = next_order
        if commit:
            obj.save()
            if hasattr(form, 'save_m2m'):
                form.save_m2m()
        return obj


TrainerPriceTierFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerPriceTier,
    form=TrainerPriceTierForm,
    formset=TrainerPriceTierInlineFormSet,
    extra=1,
    can_delete=False,
    max_num=PRICE_TIER_MAX_NUM,
    validate_max=True,
)


class OnboardingStep5MetaForm(forms.ModelForm):
    """Free consultation + “most popular” tier (radios); pricing rows come from the formset."""

    show_most_popular_tier = forms.TypedChoiceField(
        label='Highlight one price option on your public profile as “most popular”?',
        choices=[('yes', 'Yes'), ('no', 'No')],
        coerce=lambda v: v == 'yes',
        widget=forms.RadioSelect,
        required=True,
    )
    most_popular_row = forms.ChoiceField(
        label='Which option should be highlighted?',
        choices=[],
        widget=TierCaptionRadioSelect,
        required=False,
    )

    class Meta:
        model = TrainerProfile
        fields = ('free_consultation',)

    def __init__(self, *args, tier_row_captions: list[str] | None = None, tier_form_count: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if tier_row_captions is not None:
            captions = list(tier_row_captions)
        elif tier_form_count is not None:
            n = int(tier_form_count)
            captions = [f'Row {i + 1:02d}' for i in range(n)]
        else:
            n = self.instance.price_tiers.filter(order__lte=PRICE_TIER_MAX_NUM).count() + 1
            n = min(max(n, 2), PRICE_TIER_MAX_NUM + 1)
            captions = [f'Row {i + 1:02d}' for i in range(n)]
        self._tier_form_count = len(captions)
        self.fields['most_popular_row'].choices = [(str(i), cap) for i, cap in enumerate(captions)]
        if not self.is_bound:
            tiers = list(self.instance.price_tiers.filter(order__lte=PRICE_TIER_MAX_NUM).order_by('order'))
            any_pop = any(t.is_most_popular for t in tiers)
            self.initial['show_most_popular_tier'] = 'yes' if any_pop else 'no'
            if any_pop:
                max_idx = max(self._tier_form_count - 1, 0)
                for i, t in enumerate(tiers):
                    if t.is_most_popular:
                        self.initial['most_popular_row'] = str(min(i, max_idx))
                        break

    def clean(self):
        data = super().clean()
        want = data.get('show_most_popular_tier')
        row = (data.get('most_popular_row') or '').strip()
        n = getattr(self, '_tier_form_count', 0)
        valid = {str(i) for i in range(n)}
        if want:
            if row not in valid:
                self.add_error('most_popular_row', 'Choose which option to highlight.')
        return data


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
    """`show_intro_video` as Yes/No radios (clearer than a single checkbox)."""

    show_intro_video = forms.TypedChoiceField(
        label='Show intro video on your public profile',
        choices=[
            ('yes', 'Yes'),
            ('no', 'No'),
        ],
        coerce=lambda v: v == 'yes',
        widget=forms.RadioSelect,
        required=True,
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial['show_intro_video'] = 'yes' if self.instance.show_intro_video else 'no'

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
    fs = getattr(profile, 'featured_review_slot', None)
    init['show_featured_review'] = 'yes' if fs is not None else 'no'
    init['featured_review_slot'] = str(fs) if fs is not None else ''
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

    show_featured_review = forms.TypedChoiceField(
        label='Show a large standout quote on your public profile?',
        choices=[('yes', 'Yes'), ('no', 'No')],
        coerce=lambda v: v == 'yes',
        widget=forms.RadioSelect,
        required=True,
    )
    featured_review_slot = forms.ChoiceField(
        label='Which review should be the standout?',
        choices=[],
        widget=TierCaptionRadioSelect,
        required=False,
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

        data = self.data if self.is_bound else None
        slot_choices = []
        for i in range(MAX_ONBOARDING_REVIEWS):
            raw = ''
            if data is not None:
                raw = (data.get(f'review_{i}_name') or '').strip()
            if not raw:
                raw = (self.initial.get(f'review_{i}_name') or '').strip()
            if not raw:
                label = f'Review {i + 1}'
            elif len(raw) > 48:
                label = raw[:47] + '…'
            else:
                label = raw
            slot_choices.append((str(i), label))
        self.fields['featured_review_slot'].choices = slot_choices

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
                        'slot': i,
                    }
                    if fo:
                        row['focus'] = fo
                    out.append(row)
        self._reviews_json = out

        want = self.cleaned_data.get('show_featured_review')
        choice_raw = (self.cleaned_data.get('featured_review_slot') or '').strip()
        slots_saved = {r['slot'] for r in out}
        self._featured_slot = None
        if want:
            if not out:
                self.add_error(
                    'show_featured_review',
                    'Add at least one completed review first, or choose No.',
                )
            elif choice_raw not in ('0', '1', '2'):
                self.add_error(
                    'featured_review_slot',
                    'Choose which review is the standout.',
                )
            else:
                si = int(choice_raw)
                if si not in slots_saved:
                    self.add_error(
                        'featured_review_slot',
                        'Pick a review slot you have filled in and confirmed above.',
                    )
                else:
                    self._featured_slot = si
        return data

    def save_to_profile(self, profile: TrainerProfile) -> None:
        profile.client_reviews = getattr(self, '_reviews_json', [])
        profile.featured_review_slot = getattr(self, '_featured_slot', None)
        profile.save(update_fields=['client_reviews', 'featured_review_slot'])


class StaffTrainerCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'given-name'})))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'family-name'})))
