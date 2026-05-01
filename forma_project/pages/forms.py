"""
Onboarding forms for PT profile setup (7 steps). Widgets use `.forma-input` (see static_src/css/input.css).

View wiring (call `ensure_onboarding_children(profile)` before step 0 GET/POST so child rows exist):
  Step 1: OnboardingStep1Form + TrainerWhoIWorkWithFormSet (identity, tagline, bio, who I work with rows, contact, portrait)
  Step 2: OnboardingStep2QuickForm + TrainerAdditionalQualificationFormSet (up to 10 rows)
  Step 3: TrainerSpecialismFormSet (up to four rows: catalog dropdown or new name + optional description)
  Step 4: OnboardingStep4Form + TrainerGymFormSet (saves training_locations, other_areas, and up to 5 optional gym rows: name + PrimaryArea location when "Gym" is selected, or new area via ensure_for_custom_entry;
  other_areas: catalogue names and/or {name, outward}; custom entries are copied into PrimaryArea on save)
  Step 5: OnboardingStep5MetaForm + TrainerPriceTierFormSet (up to 10 tiers + one blank row to add more)
  Step 6: OnboardingStep6InstagramForm (intro video, show toggle, Instagram) + TrainerGalleryPhotoFormSet
  Step 7: OnboardingStep7ReviewsForm → TrainerProfile.client_reviews (JSON) + featured_review_slot

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
    ProofOutcomeTag,
    ProofTestimonial,
    ProfileEnquiry,
    SpecialismCatalog,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerGym,
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


class ProfileEnquiryForm(forms.ModelForm):
    """Public marketing form — name, email, optional message (see ProfileEnquiry)."""

    class Meta:
        model = ProfileEnquiry
        fields = ('name', 'email', 'message')
        labels = {
            'name': 'Name',
            'email': 'Email',
            'message': 'Anything else we should know?',
        }
        widgets = {
            'name': forms.TextInput(attrs=_forma_attrs({'autocomplete': 'name'})),
            'email': forms.EmailInput(attrs=_forma_attrs({'autocomplete': 'email'})),
            'message': forms.Textarea(
                attrs={
                    'rows': 6,
                    'class': f'{FORMA_INPUT_CLASS} min-h-[5.5rem] resize-y font-body text-[0.92rem] font-light normal-case tracking-normal text-ink',
                }
            ),
        }


class ProofTestimonialSubmissionForm(forms.ModelForm):
    """Client-facing Proof submission form for pending review."""

    outcome_tags = forms.MultipleChoiceField(
        label='Outcome tags',
        required=True,
        choices=[],
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ProofTestimonial
        fields = (
            'client_first_name',
            'client_last_initial',
            'client_job_title',
            'client_location',
            'client_specialism',
            'star_rating',
            'outcome_tags',
            'prompt_start',
            'prompt_change',
            'prompt_recommend',
            'video',
            'share_to_instagram',
        )
        labels = {
            'client_first_name': 'First name',
            'client_last_initial': 'Last initial',
            'client_job_title': 'Job title',
            'client_location': 'Location',
            'client_specialism': 'Specialism',
            'star_rating': 'Star rating',
            'prompt_start': 'Where were you when you started?',
            'prompt_change': 'What changed?',
            'prompt_recommend': 'What would you tell someone considering this practitioner?',
            'video': 'Record or upload your video',
            'share_to_instagram': 'Show me a one-tap Instagram share prompt after submit',
        }
        widgets = {
            'client_first_name': forms.TextInput(attrs=_forma_attrs({'autocomplete': 'given-name'})),
            'client_last_initial': forms.TextInput(
                attrs=_forma_attrs({'maxlength': 1, 'autocomplete': 'family-name'})
            ),
            'client_job_title': forms.TextInput(attrs=_forma_attrs({'autocomplete': 'organization-title'})),
            'client_location': forms.TextInput(attrs=_forma_attrs({'autocomplete': 'address-level2'})),
            'client_specialism': forms.TextInput(attrs=_forma_attrs({'placeholder': 'e.g. Strength training'})),
            'star_rating': forms.Select(
                choices=[(i, f'{i} star{"s" if i != 1 else ""}') for i in range(1, 6)],
                attrs=_forma_attrs(),
            ),
            'prompt_start': forms.Textarea(attrs=_forma_attrs({'rows': 4})),
            'prompt_change': forms.Textarea(attrs=_forma_attrs({'rows': 4})),
            'prompt_recommend': forms.Textarea(attrs=_forma_attrs({'rows': 4})),
            'video': forms.ClearableFileInput(
                attrs={
                    'class': FORMA_INPUT_CLASS,
                    'accept': 'video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v',
                    'capture': 'user',
                }
            ),
        }

    def __init__(self, *args, profile: TrainerProfile | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._profile = profile
        self.fields['client_job_title'].required = False
        self.fields['client_location'].required = False
        self.fields['client_specialism'].required = False
        self.fields['share_to_instagram'].required = False
        self.fields['outcome_tags'].choices = list(
            ProofOutcomeTag.objects.filter(is_active=True)
            .order_by('sort_order', 'label')
            .values_list('key', 'label')
        )

        profile_specialisms = list(dict.fromkeys(non_empty_specialisms(profile))) if profile is not None else []
        if profile_specialisms:
            self.fields['client_specialism'] = forms.ChoiceField(
                label='Specialism',
                required=False,
                choices=[('', 'Choose one (optional)')] + [(s, s) for s in profile_specialisms],
                widget=forms.Select(attrs=_forma_attrs()),
            )

    def clean_client_first_name(self):
        return (self.cleaned_data.get('client_first_name') or '').strip()

    def clean_client_last_initial(self):
        value = (self.cleaned_data.get('client_last_initial') or '').strip().upper()
        if len(value) != 1 or not value.isalpha():
            raise ValidationError('Enter one letter for last initial.')
        return value

    def clean_client_job_title(self):
        return (self.cleaned_data.get('client_job_title') or '').strip()

    def clean_client_location(self):
        return (self.cleaned_data.get('client_location') or '').strip()

    def clean_client_specialism(self):
        return (self.cleaned_data.get('client_specialism') or '').strip()

    def clean_outcome_tags(self):
        tags = list(self.cleaned_data.get('outcome_tags') or [])
        if len(tags) < 1 or len(tags) > 2:
            raise ValidationError('Choose one or two outcome tags.')
        return tags

    def clean_prompt_start(self):
        return (self.cleaned_data.get('prompt_start') or '').strip()

    def clean_prompt_change(self):
        return (self.cleaned_data.get('prompt_change') or '').strip()

    def clean_prompt_recommend(self):
        return (self.cleaned_data.get('prompt_recommend') or '').strip()

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.outcome_tags = list(self.cleaned_data.get('outcome_tags', []))
        obj.status = ProofTestimonial.STATUS_PENDING
        if commit:
            obj.save()
        return obj


class ProofVideoUploadForm(forms.Form):
    video = forms.FileField(
        label='Video',
        required=True,
        widget=forms.ClearableFileInput(
            attrs={
                'class': FORMA_INPUT_CLASS,
                'accept': 'video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v',
                'capture': 'user',
            }
        ),
    )


class ProofDetailsForm(forms.Form):
    client_first_name = forms.CharField(
        label='First name',
        max_length=80,
        widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'given-name'})),
    )
    client_last_initial = forms.CharField(
        label='Last initial',
        max_length=1,
        widget=forms.TextInput(attrs=_forma_attrs({'maxlength': 1, 'autocomplete': 'family-name'})),
    )
    client_job_title = forms.CharField(
        label='Job title',
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'organization-title'})),
    )
    star_rating = forms.IntegerField(
        label='Star rating',
        min_value=1,
        max_value=5,
        widget=forms.HiddenInput,
    )
    outcome_tags = forms.MultipleChoiceField(
        label='Outcome tags',
        required=True,
        choices=[],
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['outcome_tags'].choices = list(
            ProofOutcomeTag.objects.filter(is_active=True)
            .order_by('sort_order', 'label')
            .values_list('key', 'label')
        )

    def clean_client_first_name(self):
        return (self.cleaned_data.get('client_first_name') or '').strip()

    def clean_client_last_initial(self):
        value = (self.cleaned_data.get('client_last_initial') or '').strip().upper()
        if len(value) != 1 or not value.isalpha():
            raise ValidationError('Enter one letter for last initial.')
        return value

    def clean_client_job_title(self):
        return (self.cleaned_data.get('client_job_title') or '').strip()

    def clean_outcome_tags(self):
        tags = list(self.cleaned_data.get('outcome_tags') or [])
        if len(tags) < 1 or len(tags) > 2:
            raise ValidationError('Choose one or two outcome tags.')
        return tags


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
            'years_experience',
            'bio',
            'contact_email',
            'contact_phone',
            'contact_phone_preference',
            'portrait',
        )
        labels = {
            'years_experience': 'Years of experience',
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
            'years_experience': forms.NumberInput(
                attrs=_forma_attrs(
                    {
                        'placeholder': '7',
                        'min': 0,
                        'max': 60,
                        'inputmode': 'numeric',
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

    def clean_years_experience(self):
        raw = self.cleaned_data.get('years_experience')
        if raw in (None, ''):
            return None
        return int(raw)

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
    """Catalog dropdown + optional new name; description stays free text."""

    specialism_choice = forms.ChoiceField(
        label='Specialism',
        required=False,
        widget=forms.Select(attrs=_forma_attrs()),
    )
    new_specialism_title = forms.CharField(
        label='New specialism name',
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs=_forma_attrs(
                {
                    'placeholder': 'Type the name if you chose “Add a new specialism”',
                }
            )
        ),
    )

    class Meta:
        model = TrainerSpecialism
        fields = ('description',)
        labels = {
            'description': 'Brief description',
        }
        widgets = {
            'description': forms.Textarea(
                attrs=_forma_attrs(
                    {
                        'rows': 4,
                        'class': f'{FORMA_INPUT_CLASS} min-h-[5.5rem] resize-y leading-relaxed',
                        'placeholder': 'One sentence on what this means for clients',
                    }
                )
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rows = list(
            SpecialismCatalog.objects.filter(is_active=True)
            .order_by('title')
            .values_list('pk', 'title')
        )
        self.fields['specialism_choice'].choices = [
            ('', '— Select a specialism —'),
            *[(str(pk), title) for pk, title in rows],
            ('__new__', '+ Add a new specialism'),
        ]
        inst = self.instance
        if inst.pk:
            if inst.catalog_id:
                self.initial.setdefault('specialism_choice', str(inst.catalog_id))
            elif (inst.title or '').strip():
                t = inst.title.strip()
                cat = SpecialismCatalog.objects.filter(title__iexact=t).first()
                if cat:
                    self.initial.setdefault('specialism_choice', str(cat.pk))
                else:
                    self.initial.setdefault('specialism_choice', '__new__')
                    self.initial.setdefault('new_specialism_title', t)

    def clean_description(self):
        return (self.cleaned_data.get('description') or '').strip()

    def clean(self):
        data = super().clean()
        choice = (data.get('specialism_choice') or '').strip()
        new_t = (data.get('new_specialism_title') or '').strip()
        desc = (data.get('description') or '').strip()
        if not choice and not new_t:
            if desc:
                raise ValidationError(
                    'Select a specialism from the list (or add a new one) when you add a description.',
                )
            data['_empty_row'] = True
            return data
        if choice == '__new__':
            if not new_t:
                self.add_error('new_specialism_title', 'Enter a name for the new specialism.')
                return data
            if len(new_t) > 120:
                self.add_error('new_specialism_title', 'Keep the name to 120 characters or fewer.')
                return data
            cat, _ = SpecialismCatalog.get_or_create_for_title(new_t)
            data['_catalog'] = cat
            data['_resolved_catalog_id'] = cat.pk
            return data
        try:
            pk = int(choice)
        except (TypeError, ValueError):
            self.add_error('specialism_choice', 'Invalid choice.')
            return data
        cat = SpecialismCatalog.objects.filter(pk=pk, is_active=True).first()
        if cat is None:
            self.add_error('specialism_choice', 'Invalid choice.')
            return data
        data['_catalog'] = cat
        data['_resolved_catalog_id'] = cat.pk
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        cd = self.cleaned_data
        if cd.get('_empty_row'):
            obj.catalog_id = None
            obj.title = ''
        else:
            cat = cd['_catalog']
            obj.catalog = cat
            obj.title = cat.title[:120]
        if commit:
            obj.save()
        return obj


class TrainerSpecialismInlineFormSet(BaseInlineFormSet):
    """Cap at four rows even if legacy data created orders 5–10."""

    def get_queryset(self):
        return super().get_queryset().filter(order__lte=4)

    def clean(self):
        super().clean()
        seen: set[int] = set()
        for form in self.forms:
            cd = getattr(form, 'cleaned_data', None)
            if not cd or cd.get('_empty_row'):
                continue
            pk = cd.get('_resolved_catalog_id')
            if pk is None:
                continue
            if pk in seen:
                form.add_error('specialism_choice', 'Use a different specialism in each slot.')
            seen.add(pk)


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


class TrainerGymForm(forms.ModelForm):
    """Gym name + area from shared PrimaryArea catalogue, or add a new area (like other areas)."""

    location_add_name = forms.CharField(
        required=False,
        label='New area name',
        widget=forms.TextInput(
            attrs=_forma_attrs(
                {
                    'placeholder': 'If your area is not in the list above',
                    'autocomplete': 'off',
                }
            )
        ),
    )
    location_add_outward = forms.CharField(
        required=False,
        label='Postcode district',
        widget=forms.TextInput(
            attrs=_forma_attrs(
                {
                    'placeholder': 'e.g. SW12 or TW10',
                    'autocomplete': 'off',
                }
            )
        ),
    )

    class Meta:
        model = TrainerGym
        fields = ('name', 'location_area')
        labels = {
            'name': 'Gym name',
            'location_area': 'Location (area)',
        }
        widgets = {
            'name': forms.TextInput(
                attrs=_forma_attrs(
                    {
                        'placeholder': 'e.g. Third Space, Virgin Active',
                        'autocomplete': 'organization',
                    }
                )
            ),
            'location_area': forms.Select(
                attrs=_forma_attrs(
                    {
                        'data-gym-area-select': '1',
                    }
                )
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fields['location_area']
        f.queryset = _primary_area_queryset()
        f.required = False
        f.empty_label = 'Select an area from the list'

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        name = (cleaned.get('name') or '').strip()
        area = cleaned.get('location_area')
        add_n = (cleaned.get('location_add_name') or '').strip()
        add_o = (cleaned.get('location_add_outward') or '').strip()
        if not name and not area and not add_n and not add_o:
            return cleaned
        if add_n and area:
            self.add_error(
                None,
                'For each row, use either a location from the list or the “add area” fields — not both.',
            )
            return cleaned
        profile = None
        if self.instance and getattr(self.instance, 'profile_id', None):
            if getattr(self.instance, 'profile', None) is not None:
                profile = self.instance.profile
            else:
                profile = TrainerProfile.objects.filter(pk=self.instance.profile_id).first()
        if add_n:
            outward_val = add_o
            if outward_val:
                try:
                    validated_outward = validate_uk_postcode_outward(outward_val)
                except ValidationError as e:
                    self.add_error('location_add_outward', e)
                    return cleaned
            else:
                validated_outward = ''
            fallback = None
            if profile and profile.primary_area_id:
                fallback = profile.primary_area.district
            if not validated_outward and not fallback:
                self.add_error(
                    'location_add_outward',
                    'Enter a postcode district for this new area, or set your primary area above and try again with an empty district.',
                )
                return cleaned
            created = PrimaryArea.ensure_for_custom_entry(
                add_n,
                validated_outward,
                fallback_district=fallback,
            )
            if not created:
                self.add_error('location_add_name', 'We could not add that area. Check the name and district, then try again.')
                return cleaned
            cleaned['location_area'] = created
        if name and not cleaned.get('location_area'):
            self.add_error('location_area', 'Select a location, or add a new one below the dropdown.')
        return cleaned


class _TrainerGymFormSetBase(BaseInlineFormSet):
    pass


TrainerGymFormSet = inlineformset_factory(
    TrainerProfile,
    TrainerGym,
    form=TrainerGymForm,
    formset=_TrainerGymFormSetBase,
    extra=0,
    can_delete=False,
    max_num=5,
    min_num=0,
    validate_max=True,
)


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


MAX_ONBOARDING_REVIEWS_IN_PAYLOAD = 200


def _reviews_list_for_client_json_field(profile: TrainerProfile | None) -> list[dict]:
    """Build list for onboarding hidden JSON (name, quote, rating, focus, confirmed)."""
    out: list[dict] = []
    rows = (profile.client_reviews or []) if profile is not None else []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        r = row.get('rating')
        if isinstance(r, (int, float)) and 1 <= int(r) <= 5:
            r_int = int(r)
        else:
            r_int = None
        item = {
            'name': (row.get('name') or '')[:120],
            'quote': (row.get('quote') or '')[:600],
            'rating': r_int,
            'focus': (row.get('focus') or '').strip(),
            'confirmed': bool(row.get('confirmed')),
        }
        out.append(item)
    return out


def client_reviews_form_initial(profile: TrainerProfile) -> dict:
    init: dict = {}
    init['client_reviews_json'] = json.dumps(_reviews_list_for_client_json_field(profile))
    fs = getattr(profile, 'featured_review_slot', None)
    init['show_featured_review'] = 'yes' if fs is not None else 'no'
    if fs is not None:
        try:
            init['featured_review_index'] = int(fs)
        except (TypeError, ValueError):
            pass
    return init


class OnboardingStep7ReviewsForm(forms.Form):
    """Testimonials (name, quote, 1–5 stars, confirmation, optional focus) as JSON; persisted to TrainerProfile.client_reviews."""

    client_reviews_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )
    show_featured_review = forms.TypedChoiceField(
        label='Show a large standout quote on your public profile?',
        choices=[('yes', 'Yes'), ('no', 'No')],
        coerce=lambda v: v == 'yes',
        widget=forms.RadioSelect,
        required=True,
    )
    featured_review_index = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, profile=None, **kwargs):
        self._profile = profile
        self.focus_choices: list[tuple[str, str]] = []
        super().__init__(*args, **kwargs)
        slot_titles: list[str] = list(
            dict.fromkeys(non_empty_specialisms(profile) if profile is not None else [])
        )
        for row in (profile.client_reviews or []) if profile is not None else []:
            if isinstance(row, dict) and (row.get('focus') or '').strip():
                t = (row.get('focus') or '').strip()
                if t not in slot_titles:
                    slot_titles.append(t)
        if slot_titles:
            slot_titles = sorted(slot_titles, key=str.casefold)
            self.focus_choices = [('', 'Choose one of your specialisms')] + [(t, t) for t in slot_titles]
        else:
            self.focus_choices = [
                (
                    '',
                    'Add specialisms in step 3 to link a review to a focus area',
                )
            ]

    def clean(self):
        data = super().clean()
        out: list[dict] = []
        profile = getattr(self, '_profile', None)
        spec_titles = frozenset(non_empty_specialisms(profile)) if profile is not None else frozenset()
        prev_rows = (profile.client_reviews or []) if profile is not None else []
        raw = (self.cleaned_data.get('client_reviews_json') or '').strip()
        if raw:
            payload: list | None = None
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                self.add_error('client_reviews_json', 'The reviews data is invalid. Refresh the page and try again.')
            if payload is not None:
                if not isinstance(payload, list):
                    self.add_error('client_reviews_json', 'The reviews data is invalid.')
                elif len(payload) > MAX_ONBOARDING_REVIEWS_IN_PAYLOAD:
                    self.add_error(
                        'client_reviews_json',
                        f'You can add at most {MAX_ONBOARDING_REVIEWS_IN_PAYLOAD} reviews.',
                    )
                else:
                    for i, item in enumerate(payload):
                        if not isinstance(item, dict):
                            self.add_error('client_reviews_json', f'Review {i + 1} is invalid.')
                            out = []
                            break
                        n = (item.get('name') or '').strip()[:120]
                        q = (item.get('quote') or '').strip()[:600]
                        fo = (item.get('focus') or '').strip()
                        raw_rat = item.get('rating')
                        if isinstance(raw_rat, (int, float)):
                            rating_val = int(raw_rat) if 1 <= int(raw_rat) <= 5 else None
                        elif isinstance(raw_rat, str) and raw_rat.isdigit() and 1 <= int(raw_rat) <= 5:
                            rating_val = int(raw_rat)
                        else:
                            rating_val = None
                        confirmed = bool(item.get('confirmed') or item.get('confirm'))
                        if not n and not q and not raw_rat and not fo and not confirmed:
                            continue
                        if (not n or not q) and (n or q or raw_rat or fo or confirmed):
                            self.add_error('client_reviews_json', f'Review {i + 1}: add both reviewer name and a quote, or clear the row fully.')
                            continue
                        if not n and not q:
                            continue
                        if rating_val is None:
                            self.add_error('client_reviews_json', f'Review {i + 1}: choose a star rating from 1 to 5.')
                        if not confirmed:
                            self.add_error('client_reviews_json', f'Review {i + 1}: confirm that this is a true review.')
                        prev_f = ''
                        if i < len(prev_rows) and isinstance(prev_rows[i], dict):
                            prev_f = (prev_rows[i].get('focus') or '').strip()
                        allowed_focus = set(spec_titles)
                        if prev_f:
                            allowed_focus.add(prev_f)
                        if spec_titles and fo not in allowed_focus:
                            self.add_error('client_reviews_json', f'Review {i + 1}: pick which of your specialisms this review relates to.')
                        if (
                            rating_val is not None
                            and confirmed
                            and (not spec_titles or fo in allowed_focus)
                            and n
                            and q
                        ):
                            row = {
                                'name': n,
                                'quote': q,
                                'rating': rating_val,
                                'confirmed': True,
                                'slot': len(out),
                            }
                            if fo:
                                row['focus'] = fo
                            out.append(row)
        self._reviews_json = out

        want = self.cleaned_data.get('show_featured_review')
        idx = self.cleaned_data.get('featured_review_index')
        n_out = len(getattr(self, '_reviews_json', []))
        self._featured_slot = None
        if not want:
            return data
        if n_out < 1:
            self.add_error('show_featured_review', 'Add at least one completed review first, or choose No.')
            return data
        if not isinstance(idx, int) or idx < 0 or idx >= n_out:
            self.add_error('featured_review_index', 'Use Make standout on one of your reviews, or turn off the large quote.')
        else:
            self._featured_slot = idx
        return data

    def save_to_profile(self, profile: TrainerProfile) -> None:
        profile.client_reviews = getattr(self, '_reviews_json', [])
        profile.featured_review_slot = getattr(self, '_featured_slot', None)
        profile.save(update_fields=['client_reviews', 'featured_review_slot'])


class StaffTrainerCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'given-name'})))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_forma_attrs({'autocomplete': 'family-name'})))
